# Copyright (c) 2011 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module containing methods and classes to interact with a devserver instance.
"""

import logging
import multiprocessing
import os
import socket
import tempfile
import httplib
import urllib2

from chromite.cbuildbot import constants
from chromite.lib import cros_build_lib
from chromite.lib import osutils
from chromite.lib import timeout_util
from chromite.lib import remote_access


DEFAULT_PORT = 8080


def GenerateUpdateId(target, src, key, for_vm):
  """Returns a simple representation id of |target| and |src| paths.

  Args:
    target: Target image of the update payloads.
    src: Base image to of the delta update payloads.
    key: Private key used to sign the payloads.
    for_vm: Whether the update payloads are to be used in a VM .
  """
  update_id = target
  if src:
    update_id = '->'.join([src, update_id])

  if key:
    update_id = '+'.join([update_id, key])

  if not for_vm:
    update_id = '+'.join([update_id, 'patched_kernel'])

  return update_id


class DevServerException(Exception):
  """Base exception class of devserver errors."""


class DevServerStartupError(DevServerException):
  """Thrown when the devserver fails to start up."""


class DevServerStopError(DevServerException):
  """Thrown when the devserver fails to stop."""


class DevServerResponseError(DevServerException):
  """Thrown when the devserver responds with an error."""


class DevServerConnectionError(DevServerException):
  """Thrown when unable to connect to devserver."""


class DevServerWrapper(multiprocessing.Process):
  """A Simple wrapper around a dev server instance."""

  # Wait up to 15 minutes for the dev server to start. It can take a
  # while to start when generating payloads in parallel.
  DEV_SERVER_TIMEOUT = 900
  KILL_TIMEOUT = 10

  def __init__(self, static_dir=None, port=None, log_dir=None, src_image=None,
               board=None):
    """Initialize a DevServerWrapper instance.

    Args:
      static_dir: The static directory to be used by the devserver.
      port: The port to used by the devserver.
      log_dir: Directory to store the log files.
      src_image: The path to the image to be used as the base to
        generate delta payloads.
      board: Override board to pass to the devserver for xbuddy pathing.
    """
    super(DevServerWrapper, self).__init__()
    self.devserver_bin = 'start_devserver'
    # Set port if it is given. Otherwise, devserver will start at any
    # available port.
    self.port = None if not port else port
    self.src_image = src_image
    self.board = board
    self.tempdir = None
    self.log_dir = log_dir
    if not self.log_dir:
      self.tempdir = osutils.TempDir(
          base_dir=cros_build_lib.FromChrootPath('/tmp'),
          prefix='devserver_wrapper',
          sudo_rm=True)
      self.log_dir = self.tempdir.tempdir
    self.static_dir = static_dir
    self.log_file = os.path.join(self.log_dir, 'dev_server.log')
    self.port_file = os.path.join(self.log_dir, 'dev_server.port')
    self._pid_file = self._GetPIDFilePath()
    self._pid = None

  @classmethod
  def DownloadFile(cls, url, dest):
    """Download the file from the URL to a local path."""
    if os.path.isdir(dest):
      dest = os.path.join(dest, os.path.basename(url))

    logging.info('Downloading %s to %s', url, dest)
    osutils.WriteFile(dest, DevServerWrapper.OpenURL(url), mode='wb')

  def GetURL(self, sub_dir=None):
    """Returns the URL of this devserver instance."""
    return self.GetDevServerURL(port=self.port, sub_dir=sub_dir)

  @classmethod
  def GetDevServerURL(cls, ip=None, port=None, sub_dir=None):
    """Returns the dev server url.

    Args:
      ip: IP address of the devserver. If not set, use the IP
        address of this machine.
      port: Port number of devserver.
      sub_dir: The subdirectory of the devserver url.
    """
    ip = cros_build_lib.GetIPv4Address() if not ip else ip
    # If port number is not given, assume 8080 for backward
    # compatibility.
    port = DEFAULT_PORT if not port else port
    url = 'http://%(ip)s:%(port)s' % {'ip': ip, 'port': str(port)}
    if sub_dir:
      url += '/' + sub_dir

    return url

  @classmethod
  def OpenURL(cls, url, ignore_url_error=False, timeout=60):
    """Returns the HTTP response of a URL."""
    logging.debug('Retrieving %s', url)
    try:
      res = urllib2.urlopen(url, timeout=timeout)
    except (urllib2.HTTPError, httplib.HTTPException) as e:
      logging.error('Devserver responsded with an error!')
      raise DevServerResponseError(e)
    except (urllib2.URLError, socket.timeout) as e:
      if not ignore_url_error:
        logging.error('Cannot connect to devserver!')
        raise DevServerConnectionError(e)
    else:
      return res.read()

  @classmethod
  def WipeStaticDirectory(cls, static_dir):
    """Cleans up |static_dir|.

    Args:
      static_dir: path to the static directory of the devserver instance.
    """
    # Wipe the payload cache.
    cls.WipePayloadCache(static_dir=static_dir)
    cros_build_lib.Info('Cleaning up directory %s', static_dir)
    osutils.RmDir(static_dir, ignore_missing=True, sudo=True)

  @classmethod
  def WipePayloadCache(cls, devserver_bin='start_devserver', static_dir=None):
    """Cleans up devserver cache of payloads.

    Args:
      devserver_bin: path to the devserver binary.
      static_dir: path to use as the static directory of the devserver instance.
    """
    cros_build_lib.Info('Cleaning up previously generated payloads.')
    cmd = [devserver_bin, '--clear_cache', '--exit']
    if static_dir:
      cmd.append('--static_dir=%s' % cros_build_lib.ToChrootPath(static_dir))

    cros_build_lib.SudoRunCommand(
        cmd, enter_chroot=True, print_cmd=False, combine_stdout_stderr=True,
        redirect_stdout=True, redirect_stderr=True, cwd=constants.SOURCE_ROOT)

  def _ReadPortNumber(self):
    """Read port number from file."""
    if not self.is_alive():
      raise DevServerStartupError('Devserver terminated unexpectedly!')

    try:
      timeout_util.WaitForReturnTrue(os.path.exists,
                                     func_args=[self.port_file],
                                     timeout=self.DEV_SERVER_TIMEOUT,
                                     period=5)
    except timeout_util.TimeoutError:
      self.terminate()
      raise DevServerStartupError('Devserver portfile does not exist!')

    self.port = int(osutils.ReadFile(self.port_file).strip())

  def IsReady(self):
    """Check if devserver is up and running."""
    if not self.is_alive():
      raise DevServerStartupError('Devserver terminated unexpectedly!')

    url = os.path.join('http://%s:%d' % (remote_access.LOCALHOST_IP, self.port),
                       'check_health')
    if self.OpenURL(url, ignore_url_error=True, timeout=2):
      return True

    return False

  def _GetPIDFilePath(self):
    """Returns pid file path."""
    return tempfile.NamedTemporaryFile(prefix='devserver_wrapper',
                                       dir=self.log_dir,
                                       delete=False).name

  def _GetPID(self):
    """Returns the pid read from the pid file."""
    # Pid file was passed into the chroot.
    return osutils.ReadFile(self._pid_file).rstrip()

  def _WaitUntilStarted(self):
    """Wait until the devserver has started."""
    if not self.port:
      self._ReadPortNumber()

    try:
      timeout_util.WaitForReturnTrue(self.IsReady,
                                     timeout=self.DEV_SERVER_TIMEOUT,
                                     period=5)
    except timeout_util.TimeoutError:
      self.terminate()
      raise DevServerStartupError('Devserver did not start')

  def run(self):
    """Kicks off devserver in a separate process and waits for it to finish."""
    # Truncate the log file if it already exists.
    if os.path.exists(self.log_file):
      osutils.SafeUnlink(self.log_file, sudo=True)

    port = self.port if self.port else 0
    cmd = [self.devserver_bin,
           '--pidfile', cros_build_lib.ToChrootPath(self._pid_file),
           '--logfile', cros_build_lib.ToChrootPath(self.log_file),
           '--port=%d' % port]

    if not self.port:
      cmd.append('--portfile=%s' % cros_build_lib.ToChrootPath(self.port_file))

    if self.static_dir:
      cmd.append(
          '--static_dir=%s' % cros_build_lib.ToChrootPath(self.static_dir))

    if self.src_image:
      cmd.append('--src_image=%s' % cros_build_lib.ToChrootPath(self.src_image))

    if self.board:
      cmd.append('--board=%s' % self.board)

    result = self._RunCommand(
        cmd, enter_chroot=True,
        cwd=constants.SOURCE_ROOT, error_code_ok=True,
        redirect_stdout=True, combine_stdout_stderr=True)
    if result.returncode != 0:
      msg = ('Devserver failed to start!\n'
             '--- Start output from the devserver startup command ---\n'
             '%s'
             '--- End output from the devserver startup command ---'
             ) % result.output
      logging.error(msg)

  def Start(self):
    """Starts a background devserver and waits for it to start.

    Starts a background devserver and waits for it to start. Will only return
    once devserver has started and running pid has been read.
    """
    self.start()
    self._WaitUntilStarted()
    self._pid = self._GetPID()

  def Stop(self):
    """Kills the devserver instance with SIGTERM and SIGKILL if SIGTERM fails"""
    if not self._pid:
      logging.debug('No devserver running.')
      return

    logging.debug('Stopping devserver instance with pid %s', self._pid)
    if self.is_alive():
      self._RunCommand(['kill', self._pid], error_code_ok=True)
    else:
      logging.debug('Devserver not running!')
      return

    self.join(self.KILL_TIMEOUT)
    if self.is_alive():
      logging.warning('Devserver is unstoppable. Killing with SIGKILL')
      try:
        self._RunCommand(['kill', '-9', self._pid])
      except cros_build_lib.RunCommandError as e:
        raise DevServerStopError('Unable to stop devserver: %s' % e)

  def PrintLog(self):
    """Print devserver output to stdout."""
    print self.TailLog(num_lines='+1')

  def TailLog(self, num_lines=50):
    """Returns the most recent |num_lines| lines of the devserver log file."""
    fname = self.log_file
    if os.path.exists(fname):
      result = self._RunCommand(['tail', '-n', str(num_lines), fname],
                                capture_output=True)
      output = '--- Start output from %s ---' % fname
      output += result.output
      output += '--- End output from %s ---' % fname
      return output

  def _RunCommand(self, *args, **kwargs):
    """Runs a shell commmand."""
    kwargs.setdefault('debug_level', logging.DEBUG)
    return cros_build_lib.SudoRunCommand(*args, **kwargs)


class RemoteDevServerWrapper(DevServerWrapper):
  """A wrapper of a devserver on a remote device.

  Devserver wrapper for RemoteDevice. This wrapper kills all existing
  running devserver instances before startup, thus allowing one
  devserver running at a time.

  We assume there is no chroot on the device, thus we do not launch
  devserver inside chroot.
  """

  # Shorter timeout because the remote devserver instance does not
  # need to generate payloads.
  DEV_SERVER_TIMEOUT = 30
  KILL_TIMEOUT = 10
  PID_FILE_PATH = '/tmp/devserver_wrapper.pid'

  CHERRYPY_ERROR_MSG = """
Your device does not have cherrypy package installed; cherrypy is
necessary for launching devserver on the device. Your device may be
running an older image (<R33-4986.0.0), where cherrypy is not
installed by default.

You can fix this with one of the following three options:
  1. Update the device to a newer image with a USB stick.
  2. Run 'cros deploy device cherrypy' to install cherrpy.
  3. Run cros flash with --no-rootfs-update to update only the stateful
     parition to a newer image (with the risk that the rootfs/stateful version
    mismatch may cause some problems).
  """

  def __init__(self, remote_device, devserver_bin, **kwargs):
    """Initializes a RemoteDevserverPortal object with the remote device.

    Args:
      remote_device: A RemoteDevice object.
      devserver_bin: The path to the devserver script on the device.
      **kwargs: See DevServerWrapper documentation.
    """
    super(RemoteDevServerWrapper, self).__init__(**kwargs)
    self.device = remote_device
    self.devserver_bin = devserver_bin
    self.hostname = remote_device.hostname

  def _GetPID(self):
    """Returns the pid read from pid file."""
    result = self._RunCommand(['cat', self._pid_file])
    return result.output

  def _GetPIDFilePath(self):
    """Returns the pid filename"""
    return self.PID_FILE_PATH

  def _RunCommand(self, *args, **kwargs):
    """Runs a remote shell command.

    Args:
      *args: See RemoteAccess.RemoteDevice documentation.
      **kwargs: See RemoteAccess.RemoteDevice documentation.
    """
    kwargs.setdefault('debug_level', logging.DEBUG)
    return self.device.RunCommand(*args, **kwargs)

  def _ReadPortNumber(self):
    """Read port number from file."""
    if not self.is_alive():
      raise DevServerStartupError('Devserver terminated unexpectedly!')

    def PortFileExists():
      result = self._RunCommand(['test', '-f', self.port_file],
                                error_code_ok=True)
      return result.returncode == 0

    try:
      timeout_util.WaitForReturnTrue(PortFileExists,
                                     timeout=self.DEV_SERVER_TIMEOUT,
                                     period=5)
    except timeout_util.TimeoutError:
      self.terminate()
      raise DevServerStartupError('Devserver portfile does not exist!')

    self.port = int(self._RunCommand(
        ['cat', self.port_file], capture_output=True).output.strip())

  def IsReady(self):
    """Returns True if devserver is ready to accept requests."""
    if not self.is_alive():
      raise DevServerStartupError('Devserver terminated unexpectedly!')

    url = os.path.join('http://127.0.0.1:%d' % self.port, 'check_health')
    # Running wget through ssh because the port on the device is not
    # accessible by default.
    result = self.device.RunCommand(
        ['wget', url, '-q', '-O', '/dev/null'], error_code_ok=True)
    return result.returncode == 0

  def run(self):
    """Launches a devserver process on the device."""
    self._RunCommand(['cat', '/dev/null', '>|', self.log_file])

    port = self.port if self.port else 0
    cmd = ['python', self.devserver_bin,
           '--logfile=%s' % self.log_file,
           '--pidfile', self._pid_file,
           '--port=%d' % port,]

    if not self.port:
      cmd.append('--portfile=%s' % self.port_file)

    if self.static_dir:
      cmd.append('--static_dir=%s' % self.static_dir)

    logging.info('Starting devserver %s', self.GetDevServerURL(ip=self.hostname,
                                                               port=self.port))
    result = self._RunCommand(cmd, error_code_ok=True, redirect_stdout=True,
                              combine_stdout_stderr=True)
    if result.returncode != 0:
      msg = ('Remote devserver failed to start!\n'
             '--- Start output from the devserver startup command ---\n'
             '%s'
             '--- End output from the devserver startup command ---'
             ) % result.output
      logging.error(msg)
      if 'ImportError: No module named cherrypy' in result.output:
        logging.error(self.CHERRYPY_ERROR_MSG)

  def GetURL(self, sub_dir=None):
    """Returns the URL of this devserver instance."""
    return self.GetDevServerURL(ip=self.hostname, port=self.port,
                                sub_dir=sub_dir)

  @classmethod
  def WipePayloadCache(cls, devserver_bin='start_devserver', static_dir=None):
    """Cleans up devserver cache of payloads."""
    raise NotImplementedError()

  @classmethod
  def WipeStaticDirectory(cls, static_dir):
    """Cleans up |static_dir|."""
    raise NotImplementedError()
