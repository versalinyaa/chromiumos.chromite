# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Classes of failure types."""

import collections
import sys
import traceback

from chromite.cbuildbot import portage_utilities
from chromite.lib import cros_build_lib


class StepFailure(Exception):
  """StepFailure exceptions indicate that a cbuildbot step failed.

  Exceptions that derive from StepFailure should meet the following
  criteria:
    1) The failure indicates that a cbuildbot step failed.
    2) The necessary information to debug the problem has already been
       printed in the logs for the stage that failed.
    3) __str__() should be brief enough to include in a Commit Queue
       failure message.
  """
  def __init__(self, message=''):
    """Constructor.

    Args:
      message: An error message.
    """
    Exception.__init__(self, message)
    self.args = (message,)

  def __str__(self):
    """Stringify the message."""
    return self.message


# A namedtuple to hold information of an exception.
ExceptInfo = collections.namedtuple(
    'ExceptInfo', ['type', 'str', 'traceback'])


def CreateExceptInfo(exception, tb):
  """Creates a list of ExceptInfo objects from |exception| and |tb|.

  Creates an ExceptInfo object from |exception| and |tb|. If
  |exception| is a CompoundFailure with non-empty list of exc_infos,
  simly returns exception.exc_infos. Note that we do not preserve type
  of |exception| in this case.

  Args:
    exception: The exception.
    tb: The textual traceback.

  Returns:
    A list of ExceptInfo objects.
  """
  if issubclass(exception.__class__, CompoundFailure) and exception.exc_infos:
    return exception.exc_infos

  return [ExceptInfo(exception.__class__, str(exception), tb)]


class CompoundFailure(StepFailure):
  """An exception that contains a list of ExceptInfo objects."""

  def __init__(self, message='', exc_infos=None):
    """Initializes an CompoundFailure instance.

    Args:
      message: A string describing the failure.
      exc_infos: A list of ExceptInfo objects.
    """
    self.exc_infos = exc_infos if exc_infos else []
    if not message:
      # By default, print the type and string of each ExceptInfo object.
      message = '\n'.join(['%s: %s' % (e.type, e.str) for e in self.exc_infos])

    super(CompoundFailure, self).__init__(message=message)

  def ToFullMessage(self):
    """Returns a string with all information in self.exc_infos."""
    if self.HasEmptyList():
      # Fall back to return self.message if list is empty.
      return self.message
    else:
      # This includes the textual traceback(s).
      return '\n'.join(['{e.type}: {e.str}\n{e.traceback}'.format(e=ex) for
                        ex in self.exc_infos])

  def HasEmptyList(self):
    """Returns True if self.exc_infos is empty."""
    return not bool(self.exc_infos)

  def HasFailureType(self, cls):
    """Returns True if any of the failures matches |cls|."""
    return any(issubclass(x.type, cls) for x in self.exc_infos)

  def MatchesFailureType(self, cls):
    """Returns True if all failures matches |cls|."""
    return (not self.HasEmptyList() and
            all(issubclass(x.type, cls) for x in self.exc_infos))

  def HasFatalFailure(self, whitelist=None):
    """Determine if there are non-whitlisted failures.

    Args:
      whitelist: A list of whitelisted exception types.

    Returns:
      Returns True if any failure is not in |whitelist|.
    """
    if not whitelist:
      return not self.HasEmptyList()

    for ex in self.exc_infos:
      if all(not issubclass(ex.type, cls) for cls in whitelist):
        return True

    return False


class SetFailureType(object):
  """A wrapper to re-raise the exception as the pre-set type."""

  def __init__(self, category_exception, source_exception=None):
    """Initializes the decorator.

    Args:
      category_exception: The exception type to re-raise as. It must be
        a subclass of CompoundFailure.
      source_exception: The exception types to re-raise. By default, re-raise
        all Exception classes.
    """
    assert issubclass(category_exception, CompoundFailure)
    self.category_exception = category_exception
    self.source_exception = source_exception
    if self.source_exception is None:
      self.source_exception = Exception

  def __call__(self, functor):
    """Returns a wrapped function."""
    def wrapped_functor(*args, **kwargs):
      try:
        return functor(*args, **kwargs)
      except self.source_exception:
        # Get the information about the original exception.
        exc_type, exc_value, _ = sys.exc_info()
        exc_traceback = traceback.format_exc()
        if issubclass(exc_type, self.category_exception):
          # Do not re-raise if the exception is a subclass of the set
          # exception type because it offers more information.
          raise
        else:
          exc_infos = CreateExceptInfo(exc_value, exc_traceback)
          raise self.category_exception(exc_infos=exc_infos)

    return wrapped_functor


class RetriableStepFailure(StepFailure):
  """This exception is thrown when a step failed, but should be retried."""


class BuildScriptFailure(StepFailure):
  """This exception is thrown when a build command failed.

  It is intended to provide a shorter summary of what command failed,
  for usage in failure messages from the Commit Queue, so as to ensure
  that developers aren't spammed with giant error messages when common
  commands (e.g. build_packages) fail.
  """

  def __init__(self, exception, shortname):
    """Construct a BuildScriptFailure object.

    Args:
      exception: A RunCommandError object.
      shortname: Short name for the command we're running.
    """
    StepFailure.__init__(self)
    assert isinstance(exception, cros_build_lib.RunCommandError)
    self.exception = exception
    self.shortname = shortname
    self.args = (exception, shortname)

  def __str__(self):
    """Summarize a build command failure briefly."""
    result = self.exception.result
    if result.returncode:
      return '%s failed (code=%s)' % (self.shortname, result.returncode)
    else:
      return self.exception.msg


class PackageBuildFailure(BuildScriptFailure):
  """This exception is thrown when packages fail to build."""

  def __init__(self, exception, shortname, failed_packages):
    """Construct a PackageBuildFailure object.

    Args:
      exception: The underlying exception.
      shortname: Short name for the command we're running.
      failed_packages: List of packages that failed to build.
    """
    BuildScriptFailure.__init__(self, exception, shortname)
    self.failed_packages = set(failed_packages)
    self.args = (exception, shortname, failed_packages)

  def __str__(self):
    return ('Packages failed in %s: %s'
            % (self.shortname, ' '.join(sorted(self.failed_packages))))


class InfrastructureFailure(CompoundFailure):
  """Raised if a stage fails due to infrastructure issues."""


# Chrome OS Test Lab failures.
class TestLabFailure(InfrastructureFailure):
  """Raised if a stage fails due to hardware lab infrastructure issues."""


# Gerrit-on-Borg failures.
class GoBFailure(InfrastructureFailure):
  """Raised if a stage fails due to Gerrit-on-Borg (GoB) issues."""


class GoBQueryFailure(GoBFailure):
  """Raised if a stage fails due to Gerrit-on-Borg (GoB) query errors."""


class GoBSubmitFailure(GoBFailure):
  """Raised if a stage fails due to Gerrit-on-Borg (GoB) submission errors."""


class GoBFetchFailure(GoBFailure):
  """Raised if a stage fails due to Gerrit-on-Borg (GoB) fetch errors."""


# Google Storage failures.
class GSFailure(InfrastructureFailure):
  """Raised if a stage fails due to Google Storage (GS) issues."""


class GSUploadFailure(GSFailure):
  """Raised if a stage fails due to Google Storage (GS) upload issues."""


class GSDownloadFailure(GSFailure):
  """Raised if a stage fails due to Google Storage (GS) download issues."""


# Builder failures.
class BuilderFailure(InfrastructureFailure):
  """Raised if a stage fails due to builder issues."""


# Crash collection service failures.
class CrashCollectionFailure(InfrastructureFailure):
  """Raised if a stage fails due to crash collection services."""


class BuildFailureMessage(object):
  """Message indicating that changes failed to be validated."""

  def __init__(self, message, tracebacks, internal, reason, builder):
    """Create a BuildFailureMessage object.

    Args:
      message: The message to print.
      tracebacks: Exceptions received by individual builders, if any.
      internal: Whether this failure occurred on an internal builder.
      reason: A string describing the failure.
      builder: The builder the failure occurred on.
    """
    # Convert each of the input arguments into simple Python datastructures
    # (i.e. not generators) that can be easily pickled.
    self.message = str(message)
    self.tracebacks = tuple(tracebacks)
    self.internal = bool(internal)
    self.reason = str(reason)
    self.builder = str(builder)

  def __str__(self):
    return self.message

  def MatchesFailureType(self, cls):
    """Check if all of the tracebacks match the specified failure type."""
    for tb in self.tracebacks:
      if not isinstance(tb.exception, cls):
        if (isinstance(tb.exception, CompoundFailure) and
            tb.exception.MatchesFailureType(cls)):
          # If the exception is a CompoundFailure instance and all its
          # stored exceptions match |cls|, it meets the criteria.
          continue
        else:
          return False

    return True

  def HasFailureType(self, cls):
    """Check if any of the failures match the specified failure type."""
    for tb in self.tracebacks:
      if isinstance(tb.exception, cls):
        return True

      if (isinstance(tb.exception, CompoundFailure) and
          tb.exception.HasFailureType(cls)):
        # If the exception is a CompoundFailure instance and any of its
        # stored exceptions match |cls|, it meets the criteria.
        return True

    return False

  def IsPackageBuildFailure(self):
    """Check if all of the failures are package build failures."""
    return self.MatchesFailureType(PackageBuildFailure)

  def FindPackageBuildFailureSuspects(self, changes):
    """Figure out what changes probably caused our failures.

    We use a fairly simplistic algorithm to calculate breakage: If you changed
    a package, and that package broke, you probably broke the build. If there
    were multiple changes to a broken package, we fail them all.

    Some safeguards are implemented to ensure that bad changes are kicked out:
      1) Changes to overlays (e.g. ebuilds, eclasses, etc.) are always kicked
         out if the build fails.
      2) If a package fails that nobody changed, we kick out all of the
         changes.
      3) If any failures occur that we can't explain, we kick out all of the
         changes.

    It is certainly possible to trick this algorithm: If one developer submits
    a change to libchromeos that breaks the power_manager, and another developer
    submits a change to the power_manager at the same time, only the
    power_manager change will be kicked out. That said, in that situation, the
    libchromeos change will likely be kicked out on the next run, thanks to
    safeguard #2 above.

    Args:
      changes: List of changes to examine.

    Returns:
      Set of changes that likely caused the failure.
    """
    blame_everything = False
    suspects = set()
    for tb in self.tracebacks:
      for package in tb.exception.failed_packages:
        failed_projects = portage_utilities.FindWorkonProjects([package])
        blame_assigned = False
        for change in changes:
          if change.project in failed_projects:
            blame_assigned = True
            suspects.add(change)
        if not blame_assigned:
          blame_everything = True

    if blame_everything or not suspects:
      suspects = changes[:]
    else:
      # Never treat changes to overlays as innocent.
      suspects.update(change for change in changes
                      if '/overlays/' in change.project)
    return suspects
