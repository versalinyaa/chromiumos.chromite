#!/usr/bin/python

# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittests for config.  Needs to be run inside of chroot for mox."""

import mock
import os
import cPickle
import sys

import constants
sys.path.insert(0, constants.SOURCE_ROOT)
from chromite.cbuildbot import cbuildbot_config
from chromite.lib import cros_build_lib
from chromite.lib import cros_test_lib
from chromite.lib import git
from chromite.lib import osutils

CHROMIUM_WATCHING_URL = ('http://src.chromium.org/chrome/trunk/tools/build/'
    'masters/master.chromium.chromiumos/master_chromiumos_cros_cfg.py')


class ConfigDumpTest(cros_test_lib.TestCase):
  """Tests related to config_dump.json & cbuildbot_config.py"""

  def testDump(self):
    """Make sure the json & config are kept in sync"""
    cmd = [os.path.join(constants.CHROMITE_BIN_DIR, 'cbuildbot_view_config'),
           '-d', '--pretty']
    dump_file_path = os.path.join(constants.CHROMITE_DIR, 'cbuildbot',
                                  'config_dump.json')
    new_dump = cros_build_lib.RunCommand(cmd, capture_output=True).output
    old_dump = osutils.ReadFile(dump_file_path)
    self.assertTrue(
        new_dump == old_dump, 'config_dump.json does not match the '
        'configs defined in cbuildbot_config.py. Run '
        'bin/cbuildbot_view_config -d --pretty > cbuildbot/config_dump.json')


class ConfigPickleTest(cros_test_lib.TestCase):
  """Test that a config object is pickleable."""

  def testPickle(self):
    bc1 = cbuildbot_config.config['x86-mario-paladin']
    bc2 = cPickle.loads(cPickle.dumps(bc1))

    self.assertEquals(bc1.boards, bc2.boards)
    self.assertEquals(bc1.name, bc2.name)


class ConfigClassTest(cros_test_lib.TestCase):
  """Tests of the config class itself."""

  def testValueAccess(self):
    cfg = cbuildbot_config.config['x86-mario-paladin']

    self.assertTrue(cfg.name)
    self.assertEqual(cfg.name, cfg['name'])

    self.assertRaises(AttributeError, getattr, cfg, 'foobar')


class CBuildBotTest(cros_test_lib.MoxTestCase):
  """General tests of cbuildbot_config with respect to cbuildbot."""

  def testConfigsKeysMismatch(self):
    """Verify that all configs contain exactly the default keys.

    This checks for mispelled keys, or keys that are somehow removed.
    """
    # pylint: disable=W0212
    expected_keys = set(cbuildbot_config._default.keys())
    for build_name, config in cbuildbot_config.config.iteritems():
      config_keys = set(config.keys())

      extra_keys = config_keys.difference(expected_keys)
      self.assertFalse(extra_keys, ('Config %s has extra values %s' %
                                    (build_name, list(extra_keys))))

      missing_keys = expected_keys.difference(config_keys)
      self.assertFalse(missing_keys, ('Config %s is missing values %s' %
                                      (build_name, list(missing_keys))))

  def testConfigsHaveName(self):
    """Configs must have names set."""
    for build_name, config in cbuildbot_config.config.iteritems():
      self.assertTrue(build_name == config['name'])

  def testConfigUseflags(self):
    """Useflags must be lists.

    Strings are interpreted as arrays of characters for this, which is not
    useful.
    """
    for build_name, config in cbuildbot_config.config.iteritems():
      useflags = config.get('useflags')
      if not useflags is None:
        self.assertTrue(
          isinstance(useflags, list),
          'Config %s: useflags should be a list.' % build_name)

  def testBoards(self):
    """Verify 'boards' is explicitly set for every config."""
    for build_name, config in cbuildbot_config.config.iteritems():
      self.assertTrue(isinstance(config['boards'], (tuple, list)),
                      "Config %s doesn't have a list of boards." % build_name)
      self.assertEqual(len(set(config['boards'])), len(config['boards']),
                       'Config %s has duplicate boards.' % build_name)
      self.assertTrue(config['boards'] is not None,
                      'Config %s defines a list of boards.' % build_name)

  def testOverlaySettings(self):
    """Verify overlays and push_overlays have legal values."""
    for build_name, config in cbuildbot_config.config.iteritems():
      overlays = config['overlays']
      push_overlays = config['push_overlays']

      self.assertTrue(overlays in [None, 'public', 'private', 'both'],
                      'Config %s: has unexpected overlays value.' % build_name)
      self.assertTrue(
          push_overlays in [None, 'public', 'private', 'both'],
          'Config %s: has unexpected push_overlays value.' % build_name)

      if overlays == None:
        subset = [None]
      elif overlays == 'public':
        subset = [None, 'public']
      elif overlays == 'private':
        subset = [None, 'private']
      elif overlays == 'both':
        subset = [None, 'public', 'private', 'both']

      self.assertTrue(
          push_overlays in subset,
          'Config %s: push_overlays should be a subset of overlays.' %
              build_name)

  def testOverlayMaster(self):
    """Verify that only one master is pushing uprevs for each overlay."""
    masters = {}
    for build_name, config in cbuildbot_config.config.iteritems():
      overlays = config['overlays']
      push_overlays = config['push_overlays']
      if (overlays and push_overlays and config['uprev'] and config['master']
          and not config['branch']):
        other_master = masters.get(push_overlays)
        err_msg = 'Found two masters for push_overlays=%s: %s and %s'
        self.assertFalse(other_master,
            err_msg % (push_overlays, build_name, other_master))
        masters[push_overlays] = build_name

    if 'both' in masters:
      self.assertEquals(len(masters), 1, 'Found too many masters.')

  def testChromeRev(self):
    """Verify chrome_rev has an expected value"""
    for build_name, config in cbuildbot_config.config.iteritems():
      self.assertTrue(
          config['chrome_rev'] in constants.VALID_CHROME_REVISIONS + [None],
          'Config %s: has unexpected chrome_rev value.' % build_name)
      self.assertFalse(
          config['chrome_rev'] == constants.CHROME_REV_LOCAL,
          'Config %s: has unexpected chrome_rev_local value.' % build_name)
      if config['chrome_rev']:
        self.assertTrue(cbuildbot_config.IsPFQType(config['build_type']),
          'Config %s: has chrome_rev but is not a PFQ.' % build_name)

  def testValidVMTestType(self):
    """Verify vm_tests has an expected value"""
    for build_name, config in cbuildbot_config.config.iteritems():
      for test_type in config['vm_tests']:
        self.assertTrue(
          test_type in constants.VALID_VM_TEST_TYPES,
          'Config %s: has unexpected vm test type value.' % build_name)

  def testBuildType(self):
    """Verifies that all configs use valid build types."""
    for build_name, config in cbuildbot_config.config.iteritems():
      self.assertTrue(
          config['build_type'] in constants.VALID_BUILD_TYPES,
          'Config %s: has unexpected build_type value.' % build_name)

  def testGCCGitHash(self):
    """Verifies that gcc_githash is not set without setting latest_toolchain."""
    for build_name, config in cbuildbot_config.config.iteritems():
      if config['gcc_githash']:
        self.assertTrue(
            config['latest_toolchain'],
            'Config %s: has gcc_githash but not latest_toolchain.' % build_name)

  def testBuildToRun(self):
    """Verify we don't try to run tests without building them."""
    for build_name, config in cbuildbot_config.config.iteritems():
      self.assertFalse(
          isinstance(config['useflags'], list) and
          '-build_tests' in config['useflags'] and config['vm_tests'],
          'Config %s: has vm_tests and use -build_tests.' % build_name)

  def testSyncToChromeSdk(self):
    """Verify none of the configs build chrome sdk but don't sync chrome."""
    for build_name, config in cbuildbot_config.config.iteritems():
      if config['sync_chrome'] is not None and not config['sync_chrome']:
        self.assertFalse(
            config['chrome_sdk'],
            'Config %s: has chrome_sdk but not sync_chrome.' % build_name)

  def testNoTestSupport(self):
    """VM/unit tests shouldn't be enabled for builders without test support."""
    for build_name, config in cbuildbot_config.config.iteritems():
      if not config['tests_supported']:
        self.assertFalse(
            config['unittests'],
            'Config %s: has tests_supported but unittests=True.' % build_name)
        self.assertEqual(
            config['vm_tests'], [],
            'Config %s: has test_supported but requests vm_tests.' % build_name)

  def testHWTestsIFFArchivingHWTestArtifacts(self):
    """Make sure all configs upload artifacts that need them for hw testing."""
    for build_name, config in cbuildbot_config.config.iteritems():
      if config['hw_tests']:
        self.assertTrue(
            config['upload_hw_test_artifacts'],
            "%s is trying to run hw tests without uploading payloads." %
            build_name)

  def testHWTestValidRetry(self):
    """Verify that hw test only turn on retry when it waits for test results."""
    for build_name, config in cbuildbot_config.config.iteritems():
      for test_config in config['hw_tests']:
        self.assertFalse(test_config.async and test_config.retry,
                         '%s is trying to turn on retry for hw tests without '
                         'waiting for test results.' % build_name)

  def testValidUnifiedMasterConfig(self):
    """Make sure any unified master configurations are valid."""
    for build_name, config in cbuildbot_config.config.iteritems():
      error = 'Unified config for %s has invalid values' % build_name
      # Unified masters must be internal and must rev both overlays.
      if config['master']:
        self.assertTrue(
            config['internal'] and config['manifest_version'], error)
      elif not config['master'] and config['manifest_version']:
        # Unified slaves can rev either public or both depending on whether
        # they are internal or not.
        if not config['internal']:
          self.assertEqual(config['overlays'], constants.PUBLIC_OVERLAYS, error)
        elif cbuildbot_config.IsCQType(config['build_type']):
          self.assertEqual(config['overlays'], constants.BOTH_OVERLAYS, error)

  def testGetSlaves(self):
    """Make sure every master has a sane list of slaves"""
    for build_name, config in cbuildbot_config.config.iteritems():
      if config['master']:
        configs = cbuildbot_config.GetSlavesForMaster(config)
        self.assertEqual(
            len(map(repr, configs)), len(set(map(repr, configs))),
            'Duplicate board in slaves of %s will cause upload prebuilts'
            ' failures' % build_name)

  def testFactoryFirmwareValidity(self):
    """Ensures that firmware/factory branches have at least 1 valid name."""
    tracking_branch = git.GetChromiteTrackingBranch()
    for branch in ['firmware', 'factory']:
      if tracking_branch.startswith(branch):
        saw_config_for_branch = False
        for build_name in cbuildbot_config.config:
          if build_name.endswith('-%s' % branch):
            self.assertFalse('release' in build_name,
                             'Factory|Firmware release builders should not '
                             'contain release in their name.')
            saw_config_for_branch = True

        self.assertTrue(
            saw_config_for_branch, 'No config found for %s branch. '
            'As this is the %s branch, all release configs that are being used '
            'must end in %s.' % (branch, tracking_branch, branch))

  def testBuildTests(self):
    """Verify that we don't try to use tests without building them."""

    for build_name, config in cbuildbot_config.config.iteritems():
      if not config['build_tests']:
        for flag in ('factory_toolkit', 'vm_tests', 'hw_tests'):
          self.assertFalse(config[flag],
              'Config %s set %s without build_tests.' % (build_name, flag))

  def testAFDOInBackground(self):
    """Verify that we don't try to build or use AFDO data in the background."""
    for build_name, config in cbuildbot_config.config.iteritems():
      if config.build_packages_in_background:
        # It is unsupported to use the build_packages_in_background flags with
        # the afdo_generate or afdo_generate_min config options.
        msg = 'Config %s uses build_packages_in_background with afdo_%s'
        self.assertFalse(config.afdo_generate, msg % (build_name, 'generate'))
        self.assertFalse(config.afdo_generate_min, msg % (build_name,
                                                          'generate_min'))

  def testReleaseGroupInBackground(self):
    """Verify build_packages_in_background settings for release groups.

    For each release group, the first builder should be set to run in the
    foreground (to build binary packages), and the remainder of the builders
    should be set to run in parallel (to install the binary packages.)
    """
    for build_name, config in cbuildbot_config.config.iteritems():
      if build_name.endswith('-release-group'):
        msg = 'Config %s should not build_packages_in_background'
        self.assertFalse(config.build_packages_in_background, msg % build_name)

        self.assertTrue(config.child_configs,
            'Config %s should have child configs' % build_name)
        first_config = config.child_configs[0]
        msg = 'Primary config for %s should not build_packages_in_background'
        self.assertFalse(first_config.build_packages_in_background,
            msg % build_name)

        msg = 'Child config %s for %s should build_packages_in_background'
        for child_config in config.child_configs[1:]:
          self.assertTrue(child_config.build_packages_in_background,
              msg % (child_config.name, build_name))

  def testAFDOSameInChildConfigs(self):
    """Verify that 'afdo_use' is the same for all children in a group."""
    msg = ('Child config %s for %s should have same value for afdo_use '
           'as other children')
    for build_name, config in cbuildbot_config.config.iteritems():
      if build_name.endswith('-group'):
        prev_value = None
        self.assertTrue(config.child_configs,
            'Config %s should have child configs' % build_name)
        for child_config in config.child_configs:
          if prev_value is None:
            prev_value = child_config.afdo_use
          else:
            self.assertEqual(child_config.afdo_use, prev_value,
                msg % (child_config.name, build_name))

  def testReleaseAFDOConfigs(self):
    """Verify that <board>-release-afdo config have generate and use children.

    These configs should have a 'generate' and a 'use' child config. Also,
    any 'generate' and 'use' configs should be children of a release-afdo
    config.
    """
    msg = 'Config %s should have %s as a parent'
    parent_suffix = cbuildbot_config.CONFIG_TYPE_RELEASE_AFDO
    generate_suffix = '%s-generate' % parent_suffix
    use_suffix = '%s-use' % parent_suffix
    for build_name, config in cbuildbot_config.config.iteritems():
      if build_name.endswith(parent_suffix):
        self.assertEqual(len(config.child_configs), 2,
            'Config %s should have 2 child configs' % build_name)
        for child_config in config.child_configs:
          child_name = child_config.name
          self.assertTrue(child_name.endswith(generate_suffix) or
                          child_name.endswith(use_suffix),
                          'Config %s has wrong %s child' %
                          (build_name, child_config))
      if build_name.endswith(generate_suffix):
        parent_config_name = build_name.replace(generate_suffix,
                                                parent_suffix)
        self.assertTrue(parent_config_name in cbuildbot_config.config,
                        msg % (build_name, parent_config_name))
      if build_name.endswith(use_suffix):
        parent_config_name = build_name.replace(use_suffix,
                                                parent_suffix)
        self.assertTrue(parent_config_name in cbuildbot_config.config,
                        msg % (build_name, parent_config_name))

  def testNoGrandChildConfigs(self):
    """Verify that no child configs have a child config."""
    for build_name, config in cbuildbot_config.config.iteritems():
      for child_config in config.child_configs:
        for grandchild_config in child_config.child_configs:
          self.fail('Config %s has grandchild %s' % (build_name,
                                                     grandchild_config.name))

  def testUseChromeLKGMImpliesInternal(self):
    """Currently use_chrome_lkgm refers only to internal manifests."""
    for build_name, config in cbuildbot_config.config.iteritems():
      if config['use_chrome_lkgm']:
        self.assertTrue(config['internal'],
            'Chrome lkgm currently only works with an internal manifest: %s' % (
                build_name,))

  def testNonOverlappingConfigTypes(self):
    """Test that a config can only match one build suffix."""
    for config_type in cbuildbot_config.CONFIG_TYPE_DUMP_ORDER:
      # A longer config_type should never end with a shorter suffix.
      my_list = list(cbuildbot_config.CONFIG_TYPE_DUMP_ORDER)
      my_list.remove(config_type)
      self.assertEquals(
          cbuildbot_config.GetDisplayPosition(
              config_type, type_order=my_list),
          len(my_list))

  def testCorrectConfigTypeIndex(self):
    """Test that the correct build suffix index is returned."""
    type_order = (
        'type1',
        'donkey-type2',
        'kong-type3')

    for index, config_type in enumerate(type_order):
      config = '-'.join(['pre-fix', config_type])
      self.assertEquals(
          cbuildbot_config.GetDisplayPosition(
              config, type_order=type_order),
          index)

    # Verify suffix needs to match up to a '-'.
    self.assertEquals(
        cbuildbot_config.GetDisplayPosition(
            'pre-fix-sometype1', type_order=type_order),
        len(type_order))

  def testConfigTypesComplete(self):
    """Verify CONFIG_TYPE_DUMP_ORDER contains all valid config types."""
    for config_name in cbuildbot_config.config:
      self.assertNotEqual(
          cbuildbot_config.GetDisplayPosition(config_name),
          len(cbuildbot_config.CONFIG_TYPE_DUMP_ORDER),
          '%s did not match any types in %s' %
          (config_name, 'cbuildbot_config.CONFIG_TYPE_DUMP_ORDER'))

  def testCantBeBothTypesOfLKGM(self):
    """Using lkgm and chrome_lkgm doesn't make sense."""
    for config in cbuildbot_config.config.values():
      self.assertFalse(config['use_lkgm'] and config['use_chrome_lkgm'])

  def testNoDuplicateSlavePrebuilts(self):
    """Test that no two same-board paladin slaves upload prebuilts."""
    for cfg in cbuildbot_config.config.values():
      if (cfg['build_type'] == constants.PALADIN_TYPE and cfg['master']):
        slaves = cbuildbot_config.GetSlavesForMaster(cfg)
        prebuilt_slaves = [s for s in slaves if s['prebuilts']]
        # Dictionary from board name to builder name that uploads prebuilt
        prebuilt_slave_boards = {}
        for slave in prebuilt_slaves:
          for board in slave['boards']:
            self.assertFalse(prebuilt_slave_boards.has_key(board),
                             'Configs %s and %s both upload prebuilts for '
                             'board %s.' % (prebuilt_slave_boards.get(board),
                                            slave['name'],
                                            board))
            prebuilt_slave_boards[board] = slave['name']

  def testCantBeBothTypesOfAFDO(self):
    """Using afdo_generate and afdo_use together doesn't work."""
    for config in cbuildbot_config.config.values():
      self.assertFalse(config['afdo_use'] and config['afdo_generate'])
      self.assertFalse(config['afdo_use'] and config['afdo_generate_min'])
      self.assertFalse(config['afdo_generate'] and config['afdo_generate_min'])

  def testValidPrebuilts(self):
    """Verify all builders have valid prebuilt values."""
    for build_name, config in cbuildbot_config.config.iteritems():
      msg = 'Config %s: has unexpected prebuilts value.' % build_name
      valid_values = (False, constants.PRIVATE, constants.PUBLIC)
      self.assertTrue(config['prebuilts'] in valid_values, msg)

  def testInternalPrebuilts(self):
    for build_name, config in cbuildbot_config.config.iteritems():
      if (config['internal'] and
          config['build_type'] != constants.CHROME_PFQ_TYPE):
        msg = 'Config %s is internal but has public prebuilts.' % build_name
        self.assertNotEqual(config['prebuilts'], constants.PUBLIC, msg)

  def testValidHWTestPriority(self):
    """Verify that hw test priority is valid."""
    for build_name, config in cbuildbot_config.config.iteritems():
      for test_config in config['hw_tests']:
        self.assertTrue(
            test_config.priority in constants.HWTEST_VALID_PRIORITIES,
            '%s has an invalid hwtest priority.' % build_name)

  def testPushImagePaygenDependancies(self):
    """Paygen requires PushImage."""
    for build_name, config in cbuildbot_config.config.iteritems():

      # paygen can't complete without push_image, except for payloads
      # where --channel arguments meet the requirements.
      if config['paygen']:
        self.assertTrue(config['push_image'] or
                        config['build_type'] == constants.PAYLOADS_TYPE,
                        '%s has paygen without push_image' % build_name)

  def testPaygenTestDependancies(self):
    """paygen testing requires upload_hw_test_artifacts."""
    for build_name, config in cbuildbot_config.config.iteritems():

      # This requirement doesn't apply to payloads builds. Payloads are
      # using artifacts from a previous build.
      if build_name.endswith('-payloads'):
        continue

      if config['paygen'] and not config['paygen_skip_testing']:
        self.assertTrue(config['upload_hw_test_artifacts'],
                        '%s is not upload_hw_test_artifacts, but also not'
                        ' paygen_skip_testing' % build_name)

  def testBuildPackagesForRecoveryImage(self):
    """Tests that we build the packages required for recovery image."""
    for build_name, config in cbuildbot_config.config.iteritems():
      if config['images']:
        # If we build any image, the base image will be built, and the
        # recovery image will be created.
        if not config['packages']:
          # No packages are specified. Defaults to build all packages.
          continue

        self.assertIn('chromeos-base/chromeos-initramfs',
                      config['packages'],
                      '%s does not build chromeos-initramfs, which is required '
                      'for creating the recovery image' % build_name)


class FindFullTest(cros_test_lib.TestCase):
  """Test locating of official build for a board."""

  def _RunTest(self, board, external_expected=None, internal_expected=None):
    def check_expected(l, expected):
      if expected is not None:
        self.assertTrue(expected in [v['name'] for v in l])

    external, internal = cbuildbot_config.FindFullConfigsForBoard(board)
    self.assertFalse(
        all(v is None for v in [external_expected, internal_expected]))
    check_expected(external, external_expected)
    check_expected(internal, internal_expected)

  def _CheckCanonicalConfig(self, board, ending):
    self.assertEquals(
        '-'.join((board, ending)),
        cbuildbot_config.FindCanonicalConfigForBoard(board)['name'])

  def testExternal(self):
    """Test finding of a full builder."""
    self._RunTest('amd64-generic', external_expected='amd64-generic-full')

  def testInternal(self):
    """Test finding of a release builder."""
    self._RunTest('lumpy', internal_expected='lumpy-release')

  def testBoth(self):
    """Both an external and internal config exist for board."""
    self._RunTest('daisy', external_expected='daisy-full',
                  internal_expected='daisy-release')

  def testExternalCanonicalResolution(self):
    """Test an external canonical config."""
    self._CheckCanonicalConfig('x86-generic', 'full')

  def testInternalCanonicalResolution(self):
    """Test prefer internal over external when both exist."""
    self._CheckCanonicalConfig('daisy', 'release')

  def testAFDOCanonicalResolution(self):
    """Test prefer non-AFDO over AFDO builder."""
    self._CheckCanonicalConfig('lumpy', 'release')

  def testOneFullConfigPerBoard(self):
    """There is at most one 'full' config for a board."""
    # Verifies that there is one external 'full' and one internal 'release'
    # build per board.  This is to ensure that we fail any new configs that
    # wrongly have names like *-bla-release or *-bla-full. This case can also
    # be caught if the new suffix was added to
    # cbuildbot_config.CONFIG_TYPE_DUMP_ORDER
    # (see testNonOverlappingConfigTypes), but that's not guaranteed to happen.
    def AtMostOneConfig(board, label, configs):
      if len(configs) > 1:
        self.fail(
            'Found more than one %s config for %s: %r'
            % (label, board, [c['name'] for c in configs]))

    boards = set()
    for config in cbuildbot_config.config.itervalues():
      boards.update(config['boards'])
    # Sanity check of the boards.
    assert boards

    for b in boards:
      external, internal = cbuildbot_config.FindFullConfigsForBoard(b)
      AtMostOneConfig(b, 'external', external)
      AtMostOneConfig(b, 'internal', internal)


class OverrideForTrybotTest(cros_test_lib.TestCase):
  """Test config override functionality."""

  def _testWithOptions(self, **kwargs):
    mock_options = mock.Mock()
    for k, v in kwargs.iteritems():
      mock_options.setattr(k, v)

    for config in cbuildbot_config.config.itervalues():
      cbuildbot_config.OverrideConfigForTrybot(config, mock_options)

  def testLocalTrybot(self):
    """Override each config for local trybot."""
    self._testWithOptions(remote_trybot=False, hw_test=False)

  def testRemoteTrybot(self):
    """Override each config for remote trybot."""
    self._testWithOptions(remote_trybot=True, hw_test=False)

  def testRemoteHWTest(self):
    """Override each config for remote trybot + hwtests."""
    self._testWithOptions(remote_trybot=True, hw_test=True)

  def testChromeInternalOverride(self):
    """Verify that we are not using official Chrome for local trybots."""
    mock_options = mock.Mock()
    mock_options.remote_trybot = False
    mock_options.hw_test = False
    old = cbuildbot_config.config['x86-mario-paladin']
    new = cbuildbot_config.OverrideConfigForTrybot(old, mock_options)
    self.assertTrue(constants.USE_CHROME_INTERNAL in old['useflags'])
    self.assertFalse(constants.USE_CHROME_INTERNAL in new['useflags'])

  def testVmTestOverride(self):
    """Verify that vm_tests override for trybots pay heed to original config."""
    mock_options = mock.Mock()
    old = cbuildbot_config.config['x86-mario-paladin']
    new = cbuildbot_config.OverrideConfigForTrybot(old, mock_options)
    self.assertEquals(new['vm_tests'], [constants.SIMPLE_AU_TEST_TYPE,
                                        constants.CROS_VM_TEST_TYPE])
    old['vm_tests'] = None
    new = cbuildbot_config.OverrideConfigForTrybot(old, mock_options)
    self.assertIsNone(new['vm_tests'])


if __name__ == '__main__':
  cros_test_lib.main()
