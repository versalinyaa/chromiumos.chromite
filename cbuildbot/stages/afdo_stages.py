# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module containing the AFDO stages."""

from chromite.cbuildbot import afdo
from chromite.cbuildbot import constants
from chromite.cbuildbot import portage_utilities
from chromite.lib import alerts
from chromite.lib import cros_build_lib
from chromite.lib import gs
from chromite.cbuildbot.stages import generic_stages


class AFDODataGenerateStage(generic_stages.BoardSpecificBuilderStage,
                            generic_stages.ForgivingBuilderStage):
  """Stage that generates AFDO profile data from a perf profile."""

  def _GetCurrentArch(self):
    """Get architecture for the current board being built."""
    return self._GetPortageEnvVar('ARCH', self._current_board)

  def PerformStage(self):
    """After collecting a 'perf' profile, generate the profile in AFDO format.
    """
    super(AFDODataGenerateStage, self).PerformStage()

    board = self._current_board
    if not afdo.CanGenerateAFDOData(board):
      cros_build_lib.Warning('Board %s cannot generate its own AFDO profile.',
                             board)
      return

    arch = self._GetCurrentArch()
    buildroot = self._build_root
    gs_context = gs.GSContext()
    cpv = portage_utilities.BestVisible(constants.CHROME_CP,
                                        buildroot=buildroot)
    afdo_file = None

    # Generation of AFDO could fail for different reasons.
    # We will ignore the failures and let the master PFQ builder try
    # to find an older AFDO profile.
    try:
      if afdo.WaitForAFDOPerfData(cpv, arch, buildroot, gs_context):
        afdo_file = afdo.GenerateAFDOData(cpv, arch, board,
                                          buildroot, gs_context)
        assert afdo_file
        cros_build_lib.Info('Generated %s AFDO profile %s',
                            arch, afdo_file)
      else:
        raise afdo.MissingAFDOData('Could not find current "perf" profile. '
                                   'Master PFQ builder will try to use stale '
                                   'AFDO profile.')
    # Will let system-exiting exceptions through.
    except Exception:
      cros_build_lib.PrintBuildbotStepWarnings()
      cros_build_lib.Warning('AFDO profile generation failed with exception ',
                             exc_info=True)

      alert_msg = ('Please triage. This will become a fatal error.\n\n'
                   'arch=%s buildroot=%s\n\nURL=%s' %
                   (arch, buildroot, self._run.ConstructDashboardURL()))
      subject_msg = ('Failure in generation of AFDO Data for builder %s' %
                     self._run.config.name)
      alerts.SendEmailLog(subject_msg,
                          afdo.AFDO_ALERT_RECIPIENTS,
                          smtp_server=constants.GOLO_SMTP_SERVER,
                          message=alert_msg)
      # Re-raise whatever exception we got here. This stage will only
      # generate a warning but we want to make sure the warning is
      # generated.
      raise


class AFDOUpdateEbuildStage(generic_stages.BuilderStage):
  """Updates the Chrome ebuild with the names of the AFDO profiles."""

  def PerformStage(self):
    buildroot = self._build_root
    gs_context = gs.GSContext()
    cpv = portage_utilities.BestVisible(constants.CHROME_CP,
                                        buildroot=buildroot)
    version_number = cpv.version_no_rev.split('_')[0]

    # We need the name of one board that has been setup in this
    # builder to find the Chrome ebuild. The chrome ebuild should be
    # the same for all the boards, so just use the first one.
    board = self._boards[0]
    arch_profiles = {}
    for arch in afdo.AFDO_ARCH_GENERATORS:
      afdo_file = afdo.GetLatestAFDOFile(cpv, arch, buildroot, gs_context)
      if not afdo_file:
        raise afdo.MissingAFDOData('Could not find appropriate AFDO profile')
      state = 'current' if version_number in afdo_file else 'previous'
      cros_build_lib.Info('Found %s %s AFDO profile %s',
                          state, arch, afdo_file)
      arch_profiles[arch] = afdo_file

    # Now update the Chrome ebuild file with the AFDO profiles we found
    # for each architecture.
    afdo.UpdateChromeEbuildAFDOFile(board, arch_profiles)
