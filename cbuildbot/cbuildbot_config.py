#!/usr/bin/python
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Configuration options for various cbuildbot builders."""

# Disable relative import warning from pylint.
# pylint: disable=W0403
import constants
import copy
import json

GS_PATH_DEFAULT = 'default' # Means gs://chromeos-image-archive/ + bot_id

# Contains the valid build config suffixes in the order that they are dumped.
CONFIG_TYPE_PALADIN = 'paladin'
CONFIG_TYPE_RELEASE = 'release'
CONFIG_TYPE_FULL = 'full'
CONFIG_TYPE_FIRMWARE = 'firmware'
CONFIG_TYPE_RELEASE_AFDO = 'release-afdo'

CONFIG_TYPE_DUMP_ORDER = (
    CONFIG_TYPE_PALADIN,
    constants.PRE_CQ_BUILDER_NAME,
    'pre-cq',
    'pre-cq-launcher',
    'incremental',
    'telemetry',
    CONFIG_TYPE_FULL,
    'full-group',
    CONFIG_TYPE_RELEASE,
    'release-group',
    'release-afdo',
    'release-afdo-generate',
    'release-afdo-use',
    'sdk',
    'chromium-pfq',
    'chromium-pfq-informational',
    'chrome-perf',
    'chrome-pfq',
    'chrome-pfq-informational',
    'pre-flight-branch',
    'factory',
    CONFIG_TYPE_FIRMWARE,
    'toolchain-major',
    'toolchain-minor',
    'asan',
    'asan-informational',
    'refresh-packages',
    'test-ap',
    'test-ap-group',
    constants.BRANCH_UTIL_CONFIG,
    constants.PAYLOADS_TYPE,
)


def OverrideConfigForTrybot(build_config, options):
  """Apply trybot-specific configuration settings.

  Args:
    build_config: The build configuration dictionary to override.
      The dictionary is not modified.
    options: The options passed on the commandline.

  Returns:
    A build configuration dictionary with the overrides applied.
  """
  copy_config = copy.deepcopy(build_config)
  for my_config in [copy_config] + copy_config['child_configs']:
    my_config['uprev'] = True
    if my_config['internal']:
      my_config['overlays'] = constants.BOTH_OVERLAYS

    # Most users don't have access to the internal repositories so disable
    # them so that we use the external chromium prebuilts.
    useflags = my_config['useflags']
    if not options.remote_trybot and useflags:
      for chrome_use in official_chrome['useflags']:
        if chrome_use in useflags:
          useflags.remove(chrome_use)

    # Use the local manifest which only requires elevated access if it's really
    # needed to build.
    if not options.remote_trybot:
      my_config['manifest'] = my_config['dev_manifest']

    my_config['push_image'] = False

    if my_config['build_type'] != constants.PAYLOADS_TYPE:
      my_config['paygen'] = False

    if options.hwtest:
      if not my_config['hw_tests']:
        my_config['hw_tests'] = HWTestConfig.DefaultList(
            num=constants.HWTEST_TRYBOT_NUM, pool=constants.HWTEST_TRYBOT_POOL,
            file_bugs=False)
      else:
        for hw_config in my_config['hw_tests']:
          hw_config.num = constants.HWTEST_TRYBOT_NUM
          hw_config.pool = constants.HWTEST_TRYBOT_POOL
          hw_config.file_bugs = False
          hw_config.priority = constants.HWTEST_DEFAULT_PRIORITY

    # Default to starting with a fresh chroot on remote trybot runs.
    if options.remote_trybot:
      my_config['chroot_replace'] = True

    # In trybots, we want to always run VM tests and all unit tests, so that
    # developers will get better testing for their changes.
    if (my_config['build_type'] == constants.PALADIN_TYPE
        and my_config['tests_supported']
        and build_config['vm_tests'] is not None):
      my_config['vm_tests'] = [constants.SIMPLE_AU_TEST_TYPE,
                               constants.CROS_VM_TEST_TYPE]
      my_config['quick_unit'] = False

  return copy_config


def GetManifestVersionsRepoUrl(internal_build, read_only=False, test=False):
  """Returns the url to the manifest versions repository.

  Args:
    internal_build: Whether to use the internal repo.
    read_only: Whether the URL may be read only.  If read_only is True,
      pushing changes (even with dryrun option) may not work.
    test: Whether we should use the corresponding test repositories. These
      should be used when staging experimental features.
  """
  # pylint: disable=W0613
  if internal_build:
    url = constants.INTERNAL_GOB_URL + constants.MANIFEST_VERSIONS_INT_SUFFIX
  else:
    url = constants.EXTERNAL_GOB_URL + constants.MANIFEST_VERSIONS_SUFFIX

  if test:
    url += '-test'

  return url


def IsPFQType(b_type):
  """Returns True if this build type is a PFQ."""
  return b_type in (constants.PFQ_TYPE, constants.PALADIN_TYPE,
                    constants.CHROME_PFQ_TYPE)


def IsCQType(b_type):
  """Returns True if this build type is a Commit Queue."""
  return b_type == constants.PALADIN_TYPE


# List of usable cbuildbot configs; see add_config method.
# TODO(mtennant): This is seriously buried in this file.  Move to top
# and rename something that stands out in a file where the word "config"
# is used everywhere.
config = {}


# pylint: disable=W0102
def GetCanariesForChromeLKGM(configs=config):
  """Grabs a list of builders that are important for the Chrome LKGM."""
  builders = []
  for build_name, conf in configs.iteritems():
    if (conf['build_type'] == constants.CANARY_TYPE and
        conf['critical_for_chrome'] and not conf['child_configs']):
      builders.append(build_name)

  return builders


def FindFullConfigsForBoard(board=None):
  """Returns full builder configs for a board.

  Args:
    board: The board to match. By default, match all boards.

  Returns:
    A tuple containing a list of matching external configs and a list of
    matching internal release configs for a board.
  """
  ext_cfgs = []
  int_cfgs = []

  for name, c in config.iteritems():
    if c['boards'] and (board is None or board in c['boards']):
      if name.endswith('-%s' % CONFIG_TYPE_RELEASE) and c['internal']:
        int_cfgs.append(copy.deepcopy(c))
      elif name.endswith('-%s' % CONFIG_TYPE_FULL) and not c['internal']:
        ext_cfgs.append(copy.deepcopy(c))

  return ext_cfgs, int_cfgs


def FindCanonicalConfigForBoard(board):
  """Get the canonical cbuildbot builder config for a board."""
  ext_cfgs, int_cfgs = FindFullConfigsForBoard(board)
  # If both external and internal builds exist for this board, prefer the
  # internal one.
  both = int_cfgs + ext_cfgs
  if not both:
    raise ValueError('Invalid board specified: %s.' % board)
  return both[0]


def GetSlavesForMaster(master_config):
  """Gets the important slave builds corresponding to this master.

  A slave config is one that matches the master config in build_type,
  chrome_rev, and branch.  It also must be marked important.  For the
  full requirements see the logic in code below.

  The master itself is eligible to be a slave (of itself) if it has boards.

  Args:
    master_config: A build config for a master builder.

  Returns:
    A list of build configs corresponding to the slaves for the master
      represented by master_config.

  Raises:
    AssertionError if the given config is not a master config or it does
      not have a manifest_version.
  """
  # This is confusing.  "config" really should be capitalized in this file.
  all_configs = config

  assert master_config['manifest_version']
  assert master_config['master']

  slave_configs = []
  for build_config in all_configs.itervalues():
    if (build_config['important'] and
        build_config['manifest_version'] and
        (not build_config['master'] or build_config['boards']) and
        build_config['build_type'] == master_config['build_type'] and
        build_config['chrome_rev'] == master_config['chrome_rev'] and
        build_config['branch'] == master_config['branch']):
      slave_configs.append(build_config)

  return slave_configs


# Enumeration of valid settings; any/all config settings must be in this.
# All settings must be documented.

_settings = dict(

# name -- The name of the config.
  name=None,

# boards -- A list of boards to build.
# TODO(mtennant): Change default to [].  The unittests fail if any config
# entry does not overwrite this value to at least an empty list.
  boards=None,

# TODO(mtennant): The description sounds independent of anything to do with a
# paladin.  See if this should just be: "builder_waterfall_name".
# paladin_builder_name -- Used by paladin logic. The name of the builder on the
#                         buildbot waterfall if it differs from the config name.
#                         If None is used, defaults to config name.
  paladin_builder_name=None,

# profile -- The profile of the variant to set up and build.
  profile=None,

# master -- This bot pushes changes to the overlays.
  master=False,

# important -- If False, this flag indicates that the CQ should not check
#              whether this bot passed or failed. Set this to False if you are
#              setting up a new bot. Once the bot is on the waterfall and is
#              consistently green, mark the builder as important=True.
  important=False,

# health_threshold -- An integer. If this builder fails this many
#                     times consecutively, send an alert email to the
#                     recipients health_alert_recipients. This does
#                     not apply to tryjobs. This feature is similar to
#                     the ERROR_WATERMARK feature of upload_symbols,
#                     and it may make sense to merge the features at
#                     some point.
  health_threshold=0,

# health_alert_recipients -- List of email addresses to send health alerts to
#                            for this builder.
  health_alert_recipients=[],

# internal -- Whether this is an internal build config.
  internal=False,

# branch -- Whether this is a branched build config. Used for pfq logic.
  branch=False,

# manifest -- The name of the manifest to use. E.g., to use the buildtools
#             manifest, specify 'buildtools'.
  manifest=constants.DEFAULT_MANIFEST,

# dev_manifest -- The name of the manifest to use if we're building on a local
#                 trybot. This should only require elevated access if it's
#                 really needed to build this config.
  dev_manifest=constants.DEFAULT_MANIFEST,

# build_before_patching -- Applies only to paladin builders. If true, Sync to
#                          the manifest without applying any test patches, then
#                          do a fresh build in a new chroot. Then, apply the
#                          patches and build in the existing chroot.
  build_before_patching=False,

# do_not_apply_cq_patches -- Applies only to paladin builders. If True, Sync to
#                            the master manifest without applying any of the
#                            test patches, rather than running CommitQueueSync.
#                            This is basically ToT immediately prior to the
#                            current commit queue run.
  do_not_apply_cq_patches=False,

# sanity_check_slaves -- Applies only to master builders. List of the names of
#                        slave builders to be treated as sanity checkers. If
#                        only sanity check builders fail, then the master will
#                        ignore the failures. In a CQ run, if any of the sanity
#                        check builders fail and other builders fail as well,
#                        the master will treat the build as failed, but will
#                        not reset the ready bit of the tested patches.
  sanity_check_slaves=None,

# useflags -- emerge use flags to use while setting up the board, building
#             packages, making images, etc.
  useflags=[],

# chromeos_official -- Set the variable CHROMEOS_OFFICIAL for the build.
#                      Known to affect parallel_emerge, cros_set_lsb_release,
#                      and chromeos_version.sh. See bug chromium-os:14649
  chromeos_official=False,

# usepkg_setup_board -- Use binary packages for setup_board. (emerge --usepkg)
  usepkg_setup_board=True,

# usepkg_build_packages -- Use binary packages for build_packages.
  usepkg_build_packages=True,

# build_packages_in_background -- If set, run BuildPackages in the background
#                                 and allow subsequent stages to run in
#                                 parallel with this one.
#
#                                 For each release group, the first builder
#                                 should be set to run in the foreground (to
#                                 build binary packages), and the remainder of
#                                 the builders should be set to run in parallel
#                                 (to install the binary packages.)
  build_packages_in_background=False,

# chrome_binhost_only -- Only use binaries in build_packages for Chrome itself.
  chrome_binhost_only=False,

# sync_chrome -- Does this profile need to sync chrome?  If None, we guess based
#                on other factors.  If True/False, we always do that.
  sync_chrome=None,

# latest_toolchain -- Use the newest ebuilds for all the toolchain packages.
  latest_toolchain=False,

# gcc_githash -- This is only valid when latest_toolchain is True.
# If you set this to a commit-ish, the gcc ebuild will use it to build the
# toolchain compiler.
  gcc_githash=None,

# board_replace -- wipe and replace the board inside the chroot.
  board_replace=False,

# chroot_replace -- wipe and replace chroot, but not source.
  chroot_replace=False,

# uprev -- Uprevs the local ebuilds to build new changes since last stable.
#          build.  If master then also pushes these changes on success.
#          Note that we uprev on just about every bot config because it gives us
#          a more deterministic build system (the tradeoff being that some bots
#          build from source more frequently than if they never did an uprev).
#          This way the release/factory/etc... builders will pick up changes
#          that devs pushed before it runs, but after the correspoding PFQ bot
#          ran (which is what creates+uploads binpkgs).  The incremental bots
#          are about the only ones that don't uprev because they mimic the flow
#          a developer goes through on their own local systems.
  uprev=True,

# overlays -- Select what overlays to look at for revving and prebuilts. This
#             can be any constants.VALID_OVERLAYS.
  overlays=constants.PUBLIC_OVERLAYS,

# push_overlays -- Select what overlays to push at. This should be a subset of
#                  overlays for the particular builder.  Must be None if
#                  not a master.  There should only be one master bot pushing
#                  changes to each overlay per branch.
  push_overlays=None,

# chrome_rev -- Uprev Chrome, values of 'tot', 'stable_release', or None.
  chrome_rev=None,

# compilecheck -- Exit the builder right after checking compilation.
# TODO(mtennant): Should be something like "compile_check_only".
  compilecheck=False,

# pre_cq -- Test CLs to verify they're ready for the commit queue.
  pre_cq=False,

# signer_tests -- Runs the tests that the signer would run.
  signer_tests=False,

# unittests -- Runs unittests for packages.
  unittests=True,

# quick_unit -- If unittests is true, only run the unit tests for packages which
#               have changed since the previous build.
  quick_unit=False,

# unittest_blacklist -- A list of the packages to blacklist from unittests.
  unittest_blacklist=[],

# build_tests -- Builds autotest tests.  Must be True if vm_tests is set.
  build_tests=True,

# afdo_generate -- Generates AFDO data. Will capture a profile of chrome
#                  using a hwtest to run a predetermined set of benchmarks.
  afdo_generate=False,

# afdo_generate_min -- Generates AFDO data, builds the minimum amount
#                      of artifacts and assumes a non-distributed builder
#                      (i.e.: the whole process in a single builder).
  afdo_generate_min=False,

# afdo_update_ebuild -- Update the Chrome ebuild with the AFDO profile info.
  afdo_update_ebuild=False,

# afdo_use -- Uses AFDO data. The Chrome build will be optimized using the
#             AFDO profile information found in the chrome ebuild file.
  afdo_use=False,

# vm_tests -- A list of vm tests to run.
  vm_tests=[constants.SIMPLE_AU_TEST_TYPE],

# vm_test_runs -- The number of times to run the VMTest stage. If this is >1,
#                 then we will run the stage this many times, stopping if we
#                 encounter any failures.
  vm_test_runs=1,

# A list of HWTestConfig objects to run.
  hw_tests=[],

# upload_hw_test_artifacts -- If true, uploads artifacts for hw testing.
#                             Upload payloads for test image if the image is
#                             built. If not, dev image is used and then base
#                             image.
  upload_hw_test_artifacts=True,

# upload_standalone_images -- If true, uploads individual image tarballs.
  upload_standalone_images=True,

# gs_path -- Google Storage path to offload files to.
#            None - No upload
#            GS_PATH_DEFAULT - 'gs://chromeos-image-archive/' + bot_id
#            value - Upload to explicit path
  gs_path=GS_PATH_DEFAULT,

# TODO(sosa): Deprecate binary.
# build_type -- Type of builder.  Check constants.VALID_BUILD_TYPES.
  build_type=constants.PFQ_TYPE,

# Whether the tests for the board we are building can be run on the builder.
# Normally, we wouldn't be able to run unit and VM tests form non-x86 boards.
  tests_supported=True,

# images -- List of images we want to build -- see build_image for more details.
  images=['test'],

# factory_install_netboot -- Whether to build a netboot image.
  factory_install_netboot=True,

# factory_toolkit -- Whether to build the factory toolkit.
  factory_toolkit=True,

# packages -- Tuple of specific packages we want to build.  Most configs won't
#             specify anything here and instead let build_packages calculate.
  packages=(),

# push_image -- Do we push a final release image to chromeos-images.
  push_image=False,

# upload_symbols -- Do we upload debug symbols.
  upload_symbols=False,

# hwqual -- Whether we upload a hwqual tarball.
  hwqual=False,

# paygen -- Run a stage that generates release payloads for signed images.
  paygen=False,

# paygen_skip_testing -- If the paygen stage runs, generate tests,
#                           and schedule auto-tests for them.
  paygen_skip_testing=False,

# paygen_skip_testing -- If the paygen stage runs, don't generate any delta
#                        payloads. This is only done if deltas are broken
#                        for a given board.
  paygen_skip_delta_payloads=False,

# cpe_export -- Run a stage that generates and uploads package CPE information.
  cpe_export=True,

# debug_symbols -- Run a stage that generates and uploads debug symbols.
  debug_symbols=True,

# archive_build_debug -- Include *.debug files for debugging core files with
#                        gdb in debug.tgz. These are very large. This option
#                        only has an effect if debug_symbols and archive are
#                        set.
  archive_build_debug=False,

# archive -- Run a stage that archives build and test artifacts for developer
#            consumption.
  archive=True,

# manifest_repo_url -- git repository URL for our manifests.
#  External: https://chromium.googlesource.com/chromiumos/manifest
#  Internal: https://chrome-internal.googlesource.com/chromeos/manifest-internal
  manifest_repo_url=constants.MANIFEST_URL,

# manifest_version -- Whether we are using the manifest_version repo that stores
#                     per-build manifests.
  manifest_version=False,

# use_lkgm -- Use the Last Known Good Manifest blessed by Paladin.
  use_lkgm=False,

# use_chrome_lkgm -- LKGM for Chrome OS generated for Chrome builds that are
# blessed from canary runs.
  use_chrome_lkgm=False,

# True if this build config is critical for the chrome_lkgm decision.
  critical_for_chrome=False,

# prebuilts -- Upload prebuilts for this build. Valid values are PUBLIC,
#              PRIVATE, or False.
  prebuilts=False,

# use_sdk -- Use SDK as opposed to building the chroot from source.
  use_sdk=True,

# trybot_list -- List this config when user runs cbuildbot with --list option
#                without the --all flag.
  trybot_list=False,

# description -- The description string to print out for config when user runs
#                --list.
  description=None,

# git_sync -- Boolean that enables parameter --git-sync for upload_prebuilts.
  git_sync=False,

# child_configs -- A list of the child config groups, if applicable. See the
#                  add_group method.
  child_configs=[],

# shared_user_password -- Set shared user password for "chronos" user in built
#                         images. Use "None" (default) to remove the shared
#                         user password. Note that test images will always set
#                         the password to "test0000".
  shared_user_password=None,

# grouped -- Whether this config belongs to a config group.
  grouped=False,

# disk_layout -- layout of build_image resulting image.
#                See scripts/build_library/legacy_disk_layout.json or
#                overlay-<board>/scripts/disk_layout.json for possible values.
  disk_layout=None,

# disk_vm_layout -- layout of image_to_vm.sh resulting image. See
#                   disk_layout for more info.
  disk_vm_layout='2gb-rootfs-updatable',

# postsync_patch -- If enabled, run the PatchChanges stage.  Enabled by default.
#                   Can be overridden by the --nopatch flag.
  postsync_patch=True,

# postsync_rexec -- Reexec into the buildroot after syncing.  Enabled by
#                   default.
  postsync_reexec=True,

# create_delta_sysroot -- Create delta sysroot during ArchiveStage. Disabled by
#                          default.
  create_delta_sysroot=False,

# TODO(sosa): Collapse to one option.
# ====================== Dev installer prebuilts options =======================

# binhost_bucket -- Upload prebuilts for this build to this bucket. If it equals
#                   None the default buckets are used.
  binhost_bucket=None,

# binhost_key -- Parameter --key for upload_prebuilts. If it equals None, the
#                default values are used, which depend on the build type.
  binhost_key=None,

# binhost_base_url -- Parameter --binhost-base-url for upload_prebuilts. If it
#                     equals None, the default value is used.
  binhost_base_url=None,

# Upload dev installer prebuilts.
  dev_installer_prebuilts=False,

# Enable rootfs verification on the image.
  rootfs_verification=True,

# Build the Chrome SDK.
  chrome_sdk=False,

# If chrome_sdk is set to True, this determines whether we attempt to build
# Chrome itself with the generated SDK.
  chrome_sdk_build_chrome=True,

# If chrome_sdk is set to True, this determines whether we use goma to build
# chrome.
  chrome_sdk_goma=False,

# =============================================================================
)


class _JSONEncoder(json.JSONEncoder):
  """Json Encoder that encodes objects as their dictionaries."""
  # pylint: disable=E0202
  def default(self, obj):
    return self.encode(obj.__dict__)


class HWTestConfig(object):
  """Config object for hardware tests suites.

  Members:
    timeout: Number of seconds to wait before timing out waiting for results.
    pool: Pool to use for hw testing.
    async: Fire-and-forget suite.
    warn_only: Failure on HW tests warns only (does not generate error). If set,
               'critical' cannot be set.
    critical: Usually we consider structural failures here as OK.
    num: Maximum number of devices to use when scheduling tests in the hw lab.
    file_bugs: Should we file bugs if a test fails in a suite run.
    retry: Should we retry a test if a test fails in a suite run. Retry only
           works when async is False.
  """

  DEFAULT_HW_TEST = 'bvt'
  CQ_HW_TEST = 'bvt_cq'

  # This timeout is larger than it needs to be because of autotest overhead.
  # TODO(davidjames): Reduce this timeout once http://crbug.com/366141 is fixed.
  DEFAULT_HW_TEST_TIMEOUT = 60 * 220
  BRANCHED_HW_TEST_TIMEOUT = 10 * 60 * 60
  # Number of tests running in parallel in the AU suite.
  AU_TESTS_NUM = 2
  # Number of tests running in parallel in the QAV suite
  QAV_TEST_NUM = 2

  @classmethod
  def DefaultList(cls, **kwargs):
    """Returns a default list of HWTestConfig's for a build, with overrides for
    optional args.
    """
    # Set the number of machines for the au and qav suites. If we are
    # constrained in the number of duts in the lab, only give 1 dut to each.
    if (kwargs.get('num', constants.HWTEST_DEFAULT_NUM) >=
        constants.HWTEST_DEFAULT_NUM):
      au_dict = dict(num=cls.AU_TESTS_NUM)
      qav_dict = dict(num=cls.QAV_TEST_NUM)
    else:
      au_dict = dict(num=1)
      qav_dict = dict(num=1)

    au_kwargs = kwargs.copy()
    au_kwargs.update(au_dict)

    qav_kwargs = kwargs.copy()
    qav_kwargs.update(qav_dict)
    qav_kwargs['priority'] = constants.HWTEST_DEFAULT_PRIORITY
    qav_kwargs['retry'] = False

    # BVT + AU suite.
    return [cls(cls.DEFAULT_HW_TEST, **kwargs),
            cls(constants.HWTEST_AU_SUITE, **au_kwargs),
            cls(constants.HWTEST_QAV_SUITE, **qav_kwargs)]

  @classmethod
  def DefaultListCanary(cls, **kwargs):
    """Returns a default list of HWTestConfig's for a canary build, with
    overrides for optional args.
    """
    # Set minimum_duts default to 4, which means that lab will check the
    # number of available duts to meet the minimum requirement before creating
    # the suite job for canary builds.
    kwargs.setdefault('minimum_duts', 4)
    kwargs.setdefault('file_bugs', True)
    return cls.DefaultList(**kwargs)

  @classmethod
  def AFDOList(cls, **kwargs):
    """Returns a default list of HWTestConfig's for a AFDO build, with overrides
    for optional args.
    """
    afdo_dict = dict(pool=constants.HWTEST_CHROME_PERF_POOL,
                     timeout=120 * 60, num=1, async=True, retry=False)
    afdo_dict.update(kwargs)
    return [cls('pyauto_perf', **afdo_dict),
            cls('perf_v2', **afdo_dict)]

  @classmethod
  def DefaultListCQ(cls, **kwargs):
    """Returns a default list of HWTestConfig's for a CQ build,
    with overrides for optional args.
    """
    default_dict = dict(pool=constants.HWTEST_PALADIN_POOL, timeout=120 * 60,
                        file_bugs=False, priority=constants.HWTEST_CQ_PRIORITY,
                        minimum_duts=4)
    # Allows kwargs overrides to default_dict for cq.
    default_dict.update(kwargs)
    return [cls(cls.CQ_HW_TEST, **default_dict)]

  @classmethod
  def DefaultListPFQ(cls, **kwargs):
    """Returns a default list of HWTestConfig's for a PFQ build,
    with overrides for optional args.
    """
    default_dict = dict(pool=constants.HWTEST_PFQ_POOL, file_bugs=True,
                        priority=constants.HWTEST_PFQ_PRIORITY,
                        retry=False, minimum_duts=4)
    # Allows kwargs overrides to default_dict for pfq.
    default_dict.update(kwargs)
    return [cls(cls.DEFAULT_HW_TEST, **default_dict)]

  def __init__(self, suite, num=constants.HWTEST_DEFAULT_NUM,
               pool=constants.HWTEST_MACH_POOL, timeout=DEFAULT_HW_TEST_TIMEOUT,
               async=False, warn_only=False, critical=False, file_bugs=False,
               priority=constants.HWTEST_BUILD_PRIORITY, retry=True,
               minimum_duts=0):
    """Constructor -- see members above."""
    self.suite = suite
    self.num = num
    self.pool = pool
    self.timeout = timeout
    self.async = async
    self.warn_only = warn_only
    self.critical = critical
    self.file_bugs = file_bugs
    self.priority = priority
    self.retry = retry
    self.minimum_duts = minimum_duts
    assert not (self.warn_only and self.critical)

  def SetBranchedValues(self):
    """Changes the HW Test timeout/priority values to branched values."""
    self.timeout = max(HWTestConfig.BRANCHED_HW_TEST_TIMEOUT, self.timeout)

    # Set minimum_duts default to 0, which means that lab will not check the
    # number of available duts to meet the minimum requirement before creating
    # a suite job for branched build.
    self.minimum_duts = 0

    # Only reduce priority if it's lower.
    new_priority = constants.HWTEST_DEFAULT_PRIORITY
    if (constants.HWTEST_PRIORITIES_MAP[self.priority] >
        constants.HWTEST_PRIORITIES_MAP[new_priority]):
      self.priority = new_priority

  @property
  def timeout_mins(self):
    return int(self.timeout / 60)


def AFDORecordTest(**kwargs):
  default_dict = dict(pool=constants.HWTEST_SUITES_POOL,
                      warn_only=True, num=1, file_bugs=True,
                      timeout=constants.AFDO_GENERATE_TIMEOUT)
  # Allows kwargs overrides to default_dict for cq.
  default_dict.update(kwargs)
  return HWTestConfig(constants.HWTEST_AFDO_SUITE, **default_dict)


# TODO(mtennant): Rename this BuildConfig?
class _config(dict):
  """Dictionary of explicit configuration settings for a cbuildbot config

  Each dictionary entry is in turn a dictionary of config_param->value.

  See _settings for details on known configurations, and their documentation.
  """

  def __getattr__(self, name):
    """Support attribute-like access to each dict entry."""
    if name in self:
      return self[name]

    # Super class (dict) has no __getattr__ method, so use __getattribute__.
    return super(_config, self).__getattribute__(name)

  def GetBotId(self, remote_trybot=False):
    """Get the 'bot id' of a particular bot.

    The bot id is used to specify the subdirectory where artifacts are stored
    in Google Storage. To avoid conflicts between remote trybots and regular
    bots, we add a 'trybot-' prefix to any remote trybot runs.

    Args:
      remote_trybot: Whether this run is a remote trybot run.
    """
    return 'trybot-%s' % self.name if remote_trybot else self.name

  def derive(self, *args, **kwargs):
    """Create a new config derived from this one.

    Args:
      args: Mapping instances to mixin.
      kwargs: Settings to inject; see _settings for valid values.

    Returns:
      A new _config instance.
    """
    inherits, overrides = args, kwargs
    new_config = copy.deepcopy(self)
    for update_config in inherits:
      new_config.update(update_config)

    new_config.update(overrides)

    return copy.deepcopy(new_config)

  def add_config(self, name, *args, **kwargs):
    """Derive and add the config to cbuildbot's usable config targets

    Args:
      name: The name to label this configuration; this is what cbuildbot
            would see.
      args: See the docstring of derive.
      kwargs: See the docstring of derive.

    Returns:
      See the docstring of derive.
    """
    inherits, overrides = args, kwargs
    overrides['name'] = name
    new_config = self.derive(*inherits, **overrides)

    # Derive directly from defaults so missing values are added.
    # Store a dictionary, rather than our derivative- this is
    # to ensure any far flung consumers of the config dictionary
    # aren't affected by recent refactorings.

    config_dict = _default.derive(self, *inherits, **overrides)

    # TODO(mtennant): This is just confusing.  Some random _config object
    # (self) can add a new _config object to the global config dict.  Even if
    # self is itself not a part of the global config dict.
    config[name] = config_dict

    return new_config

  @classmethod
  def add_raw_config(cls, name, *args, **kwargs):
    return cls().add_config(name, *args, **kwargs)

  @classmethod
  def add_group(cls, name, *args, **kwargs):
    """Create a new group of build configurations.

    Args:
      name: The name to label this configuration; this is what cbuildbot
            would see.
      args: Configurations to build in this group. The first config in
            the group is considered the primary configuration and is used
            for syncing and creating the chroot.

    Returns:
      A new _config instance.
    """
    child_configs = [_default.derive(x, grouped=True) for x in args]
    return args[0].add_config(name, child_configs=child_configs, **kwargs)

_default = _config(**_settings)


# Arch-specific mixins.

# Config parameters for builders that do not run tests on the builder. Anything
# non-x86 tests will fall under this category.
non_testable_builder = _config(
  tests_supported=False,
  unittests=False,
  vm_tests=[],
)


# Builder-specific mixins

binary = _config(
  # Full builds that build fully from binaries.
  build_type=constants.BUILD_FROM_SOURCE_TYPE,
  archive_build_debug=True,
  images=['test', 'factory_install'],
  git_sync=True,
)

full = _config(
  # Full builds are test builds to show that we can build from scratch,
  # so use settings to build from scratch, and archive the results.

  usepkg_setup_board=False,
  usepkg_build_packages=False,
  chrome_sdk=True,
  chroot_replace=True,

  build_type=constants.BUILD_FROM_SOURCE_TYPE,
  archive_build_debug=True,
  images=['base', 'test', 'factory_install'],
  git_sync=True,
  trybot_list=True,
  description='Full Builds',
)

# Full builders with prebuilts.
full_prebuilts = full.derive(
  prebuilts=constants.PUBLIC,
)

pfq = _config(
  build_type=constants.PFQ_TYPE,
  important=True,
  uprev=True,
  overlays=constants.PUBLIC_OVERLAYS,
  manifest_version=True,
  trybot_list=True,
)

paladin = _config(
  important=True,
  build_type=constants.PALADIN_TYPE,
  overlays=constants.PUBLIC_OVERLAYS,
  prebuilts=constants.PUBLIC,
  manifest_version=True,
  trybot_list=True,
  description='Commit Queue',
  upload_standalone_images=False,
  chroot_replace=True,
  images=['test'],
  chrome_sdk=True,
  chrome_sdk_build_chrome=False,
)

# Used for paladin builders that build from source.
full_paladin = _config(
  board_replace=True,
  chrome_binhost_only=True,
)

# If a board has a newer instruction set, then the unit tests and VM tests
# cannot run on the builders, at least until we've implemented an emulator.
# Disable the VM tests and unit tests to be safe.
incompatible_instruction_set = _config(
  vm_tests=[],
  unittests=False,
)

# Incremental builders are intended to test the developer workflow.
# For that reason, they don't uprev.
incremental = _config(
  build_type=constants.INCREMENTAL_TYPE,
  uprev=False,
  overlays=constants.PUBLIC_OVERLAYS,
  description='Incremental Builds',
)

# This builds with more source available.
internal = _config(
  internal=True,
  overlays=constants.BOTH_OVERLAYS,
  manifest_repo_url=constants.MANIFEST_INT_URL,
)

brillo = _config(
  sync_chrome=False,
  chrome_sdk=False,
  signer_tests=False,
  # TODO(gauravsh): crbug.com/356414 Start running tests on Brillo configs.
  vm_tests=[],
  hw_tests=[],
)

moblab = brillo.derive(
  sync_chrome=None,
  chrome_sdk=True,
)

brillo_non_testable = brillo.derive(
  # Literally build the minimal possible. chromeos-initramfs is
  # required to create the recovery image. If it is not built in
  # BuildPackages, ArchiveStage will emerge it, causing race condition
  # with DebugSymbolsStage.
  packages=['virtual/target-os', 'virtual/target-os-dev',
            'chromeos-base/chromeos-initramfs'],
  images=['base', 'dev'],

  # Disable all the tests!
  build_tests=False,
  factory_toolkit=False,
  signer_tests=False,
  hw_tests=[],
  vm_tests=[],

  # Since it doesn't generate test images, payloads can't be tested.
  paygen_skip_testing=True,
)

beaglebone = non_testable_builder.derive(brillo_non_testable,
                                         rootfs_verification=False)

# This adds Chrome branding.
official_chrome = _config(
  useflags=[constants.USE_CHROME_INTERNAL],
)

# This sets chromeos_official.
official = official_chrome.derive(
  chromeos_official=True,
)

_cros_sdk = full_prebuilts.add_config('chromiumos-sdk',
  # The amd64-host has to be last as that is when the toolchains
  # are bundled up for inclusion in the sdk.
  boards=('x86-generic', 'arm-generic', 'amd64-generic'),
  build_type=constants.CHROOT_BUILDER_TYPE,
  use_sdk=False,
  trybot_list=True,
  description='Build the SDK and all the cross-compilers',
)

asan = _config(
  chroot_replace=True,
  profile='asan',
  useflags=['asan'], # see profile for more
  disk_layout='2gb-rootfs',
  disk_vm_layout='2gb-rootfs-updatable',
  vm_tests=[constants.SMOKE_SUITE_TEST_TYPE],
)

_config.add_raw_config('refresh-packages',
  boards=['x86-generic', 'arm-generic'],
  build_type=constants.REFRESH_PACKAGES_TYPE,
  description='Check upstream Gentoo for package updates',
)

incremental.add_config('x86-generic-incremental',
  boards=['x86-generic'],
)

incremental.add_config('daisy-incremental',
  non_testable_builder,
  boards=['daisy'],
)

incremental.add_config('amd64-generic-incremental',
  boards=['amd64-generic'],
  # This builder runs on a VM, so it can't run VM tests.
  vm_tests=[],
)

incremental.add_config('x32-generic-incremental',
  boards=['x32-generic'],
  # This builder runs on a VM, so it can't run VM tests.
  vm_tests=[],
)

paladin.add_config('x86-generic-paladin',
  boards=['x86-generic'],
  paladin_builder_name='x86-generic paladin',
)

paladin.add_config('amd64-generic-paladin',
  boards=['amd64-generic'],
  paladin_builder_name='amd64-generic paladin',
)

paladin.add_config('x32-generic-paladin',
  boards=['x32-generic'],
  paladin_builder_name='x32-generic paladin',
  important=False,
)

paladin.add_config('x86-generic-asan-paladin',
  asan,
  boards=['x86-generic'],
  paladin_builder_name='x86-generic asan-paladin',
  description='Paladin build with Address Sanitizer (Clang)',
  important=False,
)

paladin.add_config('mipsel-o32-generic-paladin',
  brillo_non_testable,
  boards=['mipsel-o32-generic'],
  important=False,
  paladin_builder_name='mipsel-o32-generic paladin',
)

incremental.add_config('amd64-generic-asan-paladin',
  asan,
  boards=['amd64-generic'],
  paladin_builder_name='amd64-generic asan-paladin',
  description='Paladin build with Address Sanitizer (Clang)',
  important=False,
)

telemetry = _config(
  build_type=constants.INCREMENTAL_TYPE,
  uprev=False,
  overlays=constants.PUBLIC_OVERLAYS,
  vm_tests=[constants.TELEMETRY_SUITE_TEST_TYPE],
  description='Telemetry Builds',
)

telemetry.add_config('amd64-generic-telemetry',
  boards=['amd64-generic'],
)

telemetry.add_config('arm-generic-telemetry',
  non_testable_builder,
  boards=['arm-generic'],
)

telemetry.add_config('x86-generic-telemetry',
  boards=['x86-generic'],
)

chromium_pfq = _config(
  build_type=constants.CHROME_PFQ_TYPE,
  important=True,
  uprev=False,
  overlays=constants.PUBLIC_OVERLAYS,
  manifest_version=True,
  chrome_rev=constants.CHROME_REV_LATEST,
  chrome_sdk=True,
  chroot_replace=True,
  description='Preflight Chromium Uprev & Build (public)',
)

# TODO(davidjames): Convert this to an external config once the unified master
# logic is ready.
internal_chromium_pfq = internal.derive(
  chromium_pfq,
  description='Preflight Chromium Uprev & Build (internal)',
  overlays=constants.BOTH_OVERLAYS,
  prebuilts=constants.PUBLIC,
)

internal_chromium_pfq.add_config('x86-generic-chromium-pfq',
  boards=['x86-generic'],
  master=True,
  push_overlays=constants.BOTH_OVERLAYS,
  afdo_update_ebuild=True,
)

internal_chromium_pfq.add_config('daisy-chromium-pfq',
  non_testable_builder,
  boards=['daisy'],
)

internal_chromium_pfq.add_config('amd64-generic-chromium-pfq',
  disk_layout='2gb-rootfs',
  boards=['amd64-generic'],
)

chrome_pfq = internal_chromium_pfq.derive(
  official,
  important=True,
  overlays=constants.BOTH_OVERLAYS,
  description='Preflight Chrome Uprev & Build (internal)',
  prebuilts=constants.PRIVATE,
)

chrome_pfq.add_config('alex-chrome-pfq',
  boards=['x86-alex'],
)

chrome_pfq.add_config('lumpy-chrome-pfq',
  boards=['lumpy'],
  afdo_generate=True,
  hw_tests=[AFDORecordTest()],
)

chrome_pfq.add_config('daisy_spring-chrome-pfq',
  non_testable_builder,
  boards=['daisy_spring'],
  hw_tests=HWTestConfig.DefaultListPFQ(),
)

chrome_pfq.add_config('falco-chrome-pfq',
  boards=['falco'],
  hw_tests=HWTestConfig.DefaultListPFQ(),
  important=True,
)

chrome_try = _config(
  build_type=constants.CHROME_PFQ_TYPE,
  chrome_rev=constants.CHROME_REV_TOT,
  use_lkgm=True,
  important=False,
  manifest_version=False,
  disk_vm_layout='usb',
)

chromium_info = chromium_pfq.derive(
  chrome_try,
  vm_tests=[constants.SMOKE_SUITE_TEST_TYPE],
  chrome_sdk=False,
  description='Informational Chromium Uprev & Build (public)',
)

telemetry_info = telemetry.derive(
  chrome_try,
  disk_vm_layout='2gb-rootfs-updatable',
)

chrome_info = chromium_info.derive(
  internal, official,
  description='Informational Chrome Uprev & Build (internal)',
)

chrome_perf = chrome_info.derive(
  description='Chrome Performance test bot',
  vm_tests=[],
  unittests=False,
  hw_tests=[HWTestConfig('perf_v2', pool=constants.HWTEST_CHROME_PERF_POOL,
                         timeout=90 * 60, critical=True, num=1)],
  use_chrome_lkgm=True,
  use_lkgm=False,
  useflags=official['useflags'] + ['-cros-debug'],
)

chrome_perf.add_config('daisy-chrome-perf',
  non_testable_builder,
  boards=['daisy'],
  trybot_list=True,
)

chrome_perf.add_config('lumpy-chrome-perf',
  boards=['lumpy'],
  trybot_list=True,
)

chrome_perf.add_config('parrot-chrome-perf',
  boards=['parrot'],
  trybot_list=True,
)

chromium_info_x86 = \
chromium_info.add_config('x86-generic-tot-chrome-pfq-informational',
  boards=['x86-generic'],
)

chromium_info_daisy = \
chromium_info.add_config('daisy-tot-chrome-pfq-informational',
  non_testable_builder,
  boards=['daisy'],
)

chromium_info_amd64 = \
chromium_info.add_config('amd64-generic-tot-chrome-pfq-informational',
  boards=['amd64-generic'],
)

chromium_info.add_config('x32-generic-tot-chrome-pfq-informational',
  boards=['x32-generic'],
)

telemetry_info.add_config('x86-generic-telem-chrome-pfq-informational',
  boards=['x86-generic'],
)

telemetry_info.add_config('amd64-generic-telem-chrome-pfq-informational',
  boards=['amd64-generic'],
)

chrome_info.add_config('alex-tot-chrome-pfq-informational',
  boards=['x86-alex'],
)

chrome_info.add_config('lumpy-tot-chrome-pfq-informational',
  boards=['lumpy'],
)

# WebRTC configurations.
chrome_info.add_config('alex-webrtc-chrome-pfq-informational',
  boards=['x86-alex'],
)
chrome_info.add_config('lumpy-webrtc-chrome-pfq-informational',
  boards=['lumpy'],
)
chrome_info.add_config('daisy-webrtc-chrome-pfq-informational',
  non_testable_builder,
  boards=['daisy'],
)
chromium_info_x86.add_config('x86-webrtc-chromium-pfq-informational',
  archive_build_debug=True,
)
chromium_info_amd64.add_config('amd64-webrtc-chromium-pfq-informational',
  archive_build_debug=True,
)
chromium_info_daisy.add_config('daisy-webrtc-chromium-pfq-informational',
  archive_build_debug=True,
)

_arm_release_boards = frozenset([
  'daisy',
  'daisy_skate',
  'daisy_spring',
  'nyan',
  'nyan_big',
  'nyan_blaze',
  'peach_pi',
  'peach_pit',
])
_arm_full_boards = _arm_release_boards | frozenset([
  'arm-generic',
  'arm64-generic',
])

_x86_release_boards = frozenset([
  'bayleybay',
  'beltino',
  'butterfly',
  'clapper',
  'enguarde',
  'expresso',
  'falco',
  'falco_li',
  'glimmer',
  'gnawty',
  'kip',
  'leon',
  'link',
  'lumpy',
  'mccloud',
  'monroe',
  'panther',
  'parrot',
  'parrot_ivb',
  'peppy',
  'quawks',
  'rambi',
  'samus',
  'slippy',
  'squawks',
  'stout',
  'stumpy',
  'swanky',
  'tricky',
  'winky',
  'wolf',
  'x86-alex',
  'x86-alex_he',
  'x86-mario',
  'x86-zgb',
  'x86-zgb_he',
  'zako',
])
_x86_full_boards = _x86_release_boards | frozenset([
  'amd64-generic',
  'x32-generic',
  'x86-generic',
  'x86-pineview',
])

_mips_release_boards = frozenset([
])
_mips_full_boards = _mips_release_boards | frozenset([
  'mipseb-n32-generic',
  'mipseb-n64-generic',
  'mipseb-o32-generic',
  'mipsel-n32-generic',
  'mipsel-n64-generic',
  'mipsel-o32-generic',
])

_all_release_boards = (
    _arm_release_boards |
    _x86_release_boards |
    _mips_release_boards
)
_all_full_boards = (
    _arm_full_boards |
    _x86_full_boards |
    _mips_full_boards
)

def _AddFullConfigs():
  """Add x86 and arm full configs."""
  for board in _all_full_boards:
    if board in _x86_full_boards:
      board_config = _config(
          boards=(board,),
      )
    else:
      board_config = _config(
          non_testable_builder,
          boards=(board,),
      )

    config_name = '%s-%s' % (board, CONFIG_TYPE_FULL)
    if config_name not in config:
      full_prebuilts.add_config(config_name, board_config)

    # We have to mark all autogenerated PFQs as not important so the master
    # does not wait for them.  http://crbug.com/386214
    # If you want an important PFQ, you'll have to declare it yourself.
    pfq_config = _config(
        board_config,
        important=False,
    )

    config_name = '%s-tot-chromium-pfq-informational' % board
    if config_name not in config:
      chromium_info.add_config(config_name, pfq_config)

    config_name = '%s-chromium-pfq' % board
    if config_name not in config:
      # TODO(davidjames): Convert this to an external config once the
      # unified master logic is ready.
      internal_chromium_pfq.add_config(config_name, pfq_config)

_AddFullConfigs()

_toolchain_major = _cros_sdk.add_config('toolchain-major',
  latest_toolchain=True,
  prebuilts=False,
  trybot_list=False,
  gcc_githash='svn-mirror/google/gcc-4_9-mobile',
  description='Test next major toolchain revision',
)

_toolchain_minor = _cros_sdk.add_config('toolchain-minor',
  latest_toolchain=True,
  prebuilts=False,
  trybot_list=False,
  gcc_githash='gcc.gnu.org/branches/google/gcc-4_8-mobile',
  description='Test next minor toolchain revision',
)

incremental.add_config('x86-generic-asan',
  asan,
  boards=['x86-generic'],
  description='Build with Address Sanitizer (Clang)',
  trybot_list=True,
)

chromium_info.add_config('x86-generic-tot-asan-informational',
  asan,
  boards=['x86-generic'],
  description='Full build with Address Sanitizer (Clang) on TOT',
)

incremental.add_config('amd64-generic-asan',
  asan,
  boards=['amd64-generic'],
  description='Build with Address Sanitizer (Clang)',
  trybot_list=True,
)

chromium_info.add_config('amd64-generic-tot-asan-informational',
  asan,
  boards=['amd64-generic'],
  description='Build with Address Sanitizer (Clang) on TOT',
)

incremental_beaglebone = incremental.derive(beaglebone)
incremental_beaglebone.add_config('beaglebone-incremental',
  boards=['beaglebone'],
  trybot_list=True,
  description='Incremental Beaglebone Builder',
)

#
# Internal Builds
#

internal_pfq = internal.derive(official_chrome, pfq,
  overlays=constants.BOTH_OVERLAYS,
  prebuilts=constants.PRIVATE,
)

# Because branch directories may be shared amongst builders on multiple
# branches, they must delete the chroot every time they run.
internal_pfq_branch = internal_pfq.derive(branch=True, chroot_replace=True,
                                          trybot_list=False)

internal_paladin = internal.derive(official_chrome, paladin,
  manifest=constants.OFFICIAL_MANIFEST,
  overlays=constants.BOTH_OVERLAYS,
  prebuilts=constants.PRIVATE,
  vm_tests=[],
  description=paladin['description'] + ' (internal)',
)

# Used for paladin builders with nowithdebug flag (a.k.a -cros-debug)
internal_nowithdebug_paladin = internal_paladin.derive(
  useflags=official['useflags'] + ['-cros-debug'],
  description=paladin['description'] + ' (internal, nowithdebug)',
  prebuilts=False,
)

internal_nowithdebug_paladin.add_config('x86-generic-nowithdebug-paladin',
  boards=['x86-generic'],
  paladin_builder_name='x86-generic nowithdebug-paladin',
  important=False,
)

internal_nowithdebug_paladin.add_config('amd64-generic-nowithdebug-paladin',
  boards=['amd64-generic'],
  paladin_builder_name='amd64-generic nowithdebug-paladin',
  important=False,
)

internal_nowithdebug_paladin.add_config('x86-mario-nowithdebug-paladin',
  boards=['x86-mario'],
  paladin_builder_name='x86-mario nowithdebug-paladin',
)

pre_cq = internal_paladin.derive(
  build_type=constants.INCREMENTAL_TYPE,
  build_packages_in_background=True,
  pre_cq=True,
  archive=False,
  debug_symbols=False,
  prebuilts=False,
  cpe_export=False,
  vm_tests=[constants.SMOKE_SUITE_TEST_TYPE],
  description='Verifies compilation, vm/unit tests, and building an image',
)

# Pre-CQ targets that only check compilation.
compile_only_pre_cq = pre_cq.derive(
  description='Verifies compilation only',
  compilecheck=True,
  unittests=False,
)

# TODO(davidjames): Add peach_pit, nyan, and beaglebone to pre-cq.
_config.add_group(constants.PRE_CQ_BUILDER_NAME,
  # amd64 w/kernel 3.10.
  pre_cq.add_config('rambi-pre-cq', boards=['rambi']),
  # daisy w/kernel 3.8.
  pre_cq.add_config('daisy_spring-pre-cq', non_testable_builder,
                    boards=['daisy_spring']),

  # lumpy w/kernel 3.8.
  compile_only_pre_cq.add_config('lumpy-pre-cq', non_testable_builder,
                                 boards=['lumpy']),
  # amd64 w/kernel 3.4.
  compile_only_pre_cq.add_config('parrot-pre-cq', boards=['parrot']),
)

internal_paladin.add_config('pre-cq-launcher',
  boards=[],
  build_type=constants.PRE_CQ_LAUNCHER_TYPE,
  description='Launcher for Pre-CQ builders',
  trybot_list=False,
  manifest_version=False,
  # Every Pre-CQ launch failure should send out an alert.
  health_threshold=1,
  health_alert_recipients=['chromeos-build-alerts@google.com'],
)

internal_paladin.add_config(constants.BRANCH_UTIL_CONFIG,
  boards=[],
  # Disable postsync_patch to prevent conflicting patches from being applied -
  # e.g., patches from 'master' branch being applied to a branch.
  postsync_patch=False,
  # Disable postsync_reexec to continue running the 'master' branch chromite
  # for all stages, rather than the chromite in the branch buildroot.
  postsync_reexec=False,
  build_type=constants.CREATE_BRANCH_TYPE,
  description='Used for creating/deleting branches (TPMs only)',
)

# Internal incremental builders don't use official chrome because we want
# to test the developer workflow.
internal_incremental = internal.derive(
  incremental,
  overlays=constants.BOTH_OVERLAYS,
  description='Incremental Builds (internal)',
)

internal_pfq_branch.add_config('x86-alex-pre-flight-branch',
  master=True,
  push_overlays=constants.BOTH_OVERLAYS,
  boards=['x86-alex'],
)

# A test-ap image is just a test image with a special profile enabled.
# Note that each board enabled for test-ap use has to have the testbed-ap
# profile linked to from its private overlay.
_test_ap = internal.derive(
  description='WiFi AP images used in testing',
  profile='testbed-ap',
  vm_tests=[],
)

_config.add_group('test-ap-group',
  _test_ap.add_config('stumpy-test-ap', boards=['stumpy']),
  _test_ap.add_config('panther-test-ap', boards=['panther']),
)

### Master paladin (CQ builder).

internal_paladin.add_config('master-paladin',
  boards=[],
  master=True,
  push_overlays=constants.BOTH_OVERLAYS,
  description='Commit Queue master (all others are slaves)',

  # This name should remain synced with with the name used in
  # build_internals/masters/master.chromeos/board_config.py.
  # TODO(mtennant): Fix this.  There should be some amount of auto-
  # configuration in the board_config.py code.
  paladin_builder_name='CQ master',
  health_threshold=3,
  health_alert_recipients=['chromeos-build-alerts@google.com'],
  sanity_check_slaves=['link-tot-paladin'],
  trybot_list=False,
)

### Other paladins (CQ builders).
# These are slaves of the master paladin by virtue of matching
# in a few config values (e.g. 'build_type', 'branch', etc).  If
# they are not 'important' then they are ignored slaves.
# TODO(mtennant): This master-slave relationship should be specified
# here in the configuration, rather than GetSlavesForMaster().
# Something like the following:
# master_paladin = internal_paladin.add_config(...)
# master_paladin.AddSlave(internal_paladin.add_config(...))

# Sanity check builder, part of the CQ but builds without the patches
# under test.
internal_paladin.add_config('link-tot-paladin',
  boards=['link'],
  paladin_builder_name='link ToT paladin',
  do_not_apply_cq_patches=True,
  prebuilts=False,
  hw_tests=HWTestConfig.DefaultListCQ(pool=constants.HWTEST_TOT_PALADIN_POOL),
)

internal_paladin.add_config('x86-mario-paladin',
  boards=['x86-mario'],
  paladin_builder_name='x86-mario paladin',
  vm_tests=[constants.SIMPLE_AU_TEST_TYPE],
)

internal_paladin.add_config('x86-alex-paladin',
  boards=['x86-alex'],
  paladin_builder_name='x86-alex paladin',
  hw_tests=HWTestConfig.DefaultListCQ(),
)

internal_paladin.add_config('beltino-paladin',
  boards=['beltino'],
  paladin_builder_name='beltino paladin',
  important=False,
)

# x86 full compile
internal_paladin.add_config('butterfly-paladin',
  full_paladin,
  boards=['butterfly'],
  paladin_builder_name='butterfly paladin',
)

internal_paladin.add_config('clapper-paladin',
  boards=['clapper'],
  paladin_builder_name='clapper paladin',
  important=False,
)

internal_paladin.add_config('enguarde-paladin',
  boards=['enguarde'],
  paladin_builder_name='enguarde paladin',
  important=False,
)

internal_paladin.add_config('expresso-paladin',
  boards=['expresso'],
  paladin_builder_name='expresso paladin',
  important=False,
)

# amd64 full compile
internal_paladin.add_config('falco-paladin',
  full_paladin,
  boards=['falco'],
  paladin_builder_name='falco paladin',
)

internal_paladin.add_config('fox_wtm2-paladin',
  boards=['fox_wtm2'],
  paladin_builder_name='fox_wtm2 paladin',
  important=False,
)

internal_paladin.add_config('glimmer-paladin',
  boards=['glimmer'],
  paladin_builder_name='glimmer paladin',
  important=False,
)

internal_paladin.add_config('gnawty-paladin',
  boards=['gnawty'],
  paladin_builder_name='gnawty paladin',
  important=False,
)

internal_paladin.add_config('kip-paladin',
  boards=['kip'],
  paladin_builder_name='kip paladin',
  important=False,
)

internal_paladin.add_config('leon-paladin',
  boards=['leon'],
  paladin_builder_name='leon paladin',
)

internal_paladin.add_config('link-paladin',
  boards=['link'],
  paladin_builder_name='link paladin',
  hw_tests=HWTestConfig.DefaultListCQ(),
)

internal_paladin.add_config('lumpy-paladin',
  boards=['lumpy'],
  paladin_builder_name='lumpy paladin',
  hw_tests=HWTestConfig.DefaultListCQ(),
)

internal_paladin.add_config('lumpy-incremental-paladin',
  boards=['lumpy'],
  paladin_builder_name='lumpy incremental paladin',
  build_before_patching=True,
  chroot_replace=False,
  prebuilts=False,
  compilecheck=True,
  unittests=False,
)

internal_paladin.add_config('parrot-paladin',
  boards=['parrot'],
  paladin_builder_name='parrot paladin',
  hw_tests=HWTestConfig.DefaultListCQ(),
)

internal_paladin.add_config('rambi-paladin',
  boards=['rambi'],
  paladin_builder_name='rambi paladin',
)

internal_paladin.add_config('samus-paladin',
  boards=['samus'],
  paladin_builder_name='samus paladin',
)

internal_paladin.add_config('squawks-paladin',
  boards=['squawks'],
  paladin_builder_name='squawks paladin',
  important=False,
)

internal_paladin.add_config('swanky-paladin',
  boards=['swanky'],
  paladin_builder_name='swanky paladin',
  important=False,
)

internal_paladin.add_config('quawks-paladin',
  boards=['quawks'],
  paladin_builder_name='quawks paladin',
  important=False,
)

internal_paladin.add_config('peppy-paladin',
  boards=['peppy'],
  paladin_builder_name='peppy paladin',
  vm_tests=[constants.DEV_MODE_TEST_TYPE],
)

internal_paladin.add_config('slippy-paladin',
  boards=['slippy'],
  paladin_builder_name='slippy paladin',
  important=False,
)

internal_paladin.add_config('monroe-paladin',
  boards=['monroe'],
  paladin_builder_name='monroe paladin',
)

internal_paladin.add_config('panther-paladin',
  boards=['panther'],
  paladin_builder_name='panther paladin',
)

internal_paladin.add_config('stout-paladin',
  boards=['stout'],
  paladin_builder_name='stout paladin',
  vm_tests=[constants.CROS_VM_TEST_TYPE],
)

internal_paladin.add_config('stumpy-paladin',
  boards=['stumpy'],
  paladin_builder_name='stumpy paladin',
  hw_tests=HWTestConfig.DefaultListCQ(),
)

internal_paladin.add_config('winky-paladin',
  boards=['winky'],
  paladin_builder_name='winky paladin',
  important=False,
)

internal_paladin.add_config('wolf-paladin',
  boards=['wolf'],
  paladin_builder_name='wolf paladin',
  hw_tests=HWTestConfig.DefaultListCQ(),
)

internal_paladin.add_config('x86-zgb-paladin',
  boards=['x86-zgb'],
  important=False,
  paladin_builder_name='x86-zgb paladin',
)

internal_paladin.add_config('link_freon-paladin',
  boards=['link_freon'],
  paladin_builder_name='link_freon paladin',
)

internal_paladin.add_config('stumpy_moblab-paladin',
  moblab,
  boards=['stumpy_moblab'],
  paladin_builder_name='stumpy_moblab paladin',
)

internal_paladin.add_config('rush-paladin',
  boards=['rush'],
  paladin_builder_name='rush paladin',
  important=False,
)


### Paladins (CQ builders) which do not run VM or Unit tests on the builder
### itself.
internal_notest_paladin = internal_paladin.derive(non_testable_builder)

internal_notest_paladin.add_config('daisy-paladin',
  boards=['daisy'],
  paladin_builder_name='daisy paladin',
  hw_tests=HWTestConfig.DefaultListCQ(),
)

internal_notest_paladin.add_config('daisy_spring-paladin',
  full_paladin,
  boards=['daisy_spring'],
  paladin_builder_name='daisy_spring paladin',
  hw_tests=HWTestConfig.DefaultListCQ(),
)

internal_notest_paladin.add_config('peach_pit-paladin',
  boards=['peach_pit'],
  paladin_builder_name='peach_pit paladin',
  hw_tests=HWTestConfig.DefaultListCQ(),
)

internal_notest_paladin.add_config('nyan-paladin',
  boards=['nyan'],
  paladin_builder_name='nyan paladin',
)

internal_notest_paladin.add_config('storm-paladin',
  brillo_non_testable,
  boards=['storm'],
  paladin_builder_name='storm paladin',
)

internal_brillo_paladin = internal_paladin.derive(brillo)

internal_brillo_paladin.add_config('duck-paladin',
  boards=['duck'],
  paladin_builder_name='duck paladin',
  trybot_list=True,
)

external_brillo_paladin = paladin.derive(brillo)

external_brillo_paladin.add_config('gizmo-paladin',
  boards=['gizmo'],
  paladin_builder_name='gizmo paladin',
  trybot_list=True,
  important=False,
)

external_brillo_paladin.add_config('panther_embedded-minimal-paladin',
  boards=['panther_embedded'],
  paladin_builder_name='panther_embedded-minimal paladin',
  profile='minimal',
  important=False,
  trybot_list=True,
)

internal_beaglebone_paladin = internal_paladin.derive(beaglebone)

internal_beaglebone_paladin.add_config('beaglebone-paladin',
  boards=['beaglebone'],
  paladin_builder_name='beaglebone paladin',
  trybot_list=True,
)

internal_beaglebone_paladin.add_config('beaglebone_servo-paladin',
  boards=['beaglebone_servo'],
  paladin_builder_name='beaglebone_servo paladin',
  important=False,
)

internal_incremental.add_config('mario-incremental',
  boards=['x86-mario'],
)

_toolchain_major.add_config('internal-toolchain-major', internal, official,
  boards=('x86-alex', 'stumpy', 'daisy'),
  use_lkgm=True,
  useflags=[constants.USE_CHROME_INTERNAL],
  build_tests=True,
  description=_toolchain_major['description'] + ' (internal)',
)

_toolchain_minor.add_config('internal-toolchain-minor', internal, official,
  boards=('x86-alex', 'stumpy', 'daisy'),
  use_lkgm=True,
  useflags=[constants.USE_CHROME_INTERNAL],
  build_tests=True,
  description=_toolchain_minor['description'] + ' (internal)',
)

_release = full.derive(official, internal,
  build_type=constants.CANARY_TYPE,
  useflags=official['useflags'] + ['-cros-debug', '-highdpi'],
  build_tests=True,
  manifest=constants.OFFICIAL_MANIFEST,
  manifest_version=True,
  images=['base', 'test', 'factory_install'],
  push_image=True,
  upload_symbols=True,
  binhost_bucket='gs://chromeos-dev-installer',
  binhost_key='RELEASE_BINHOST',
  binhost_base_url=
    'https://commondatastorage.googleapis.com/chromeos-dev-installer',
  dev_installer_prebuilts=True,
  git_sync=False,
  vm_tests=[constants.SMOKE_SUITE_TEST_TYPE, constants.DEV_MODE_TEST_TYPE,
            constants.CROS_VM_TEST_TYPE],
  disk_vm_layout='usb',
  hw_tests=HWTestConfig.DefaultListCanary(),
  paygen=True,
  signer_tests=True,
  trybot_list=True,
  hwqual=True,
  description="Release Builds (canary) (internal)",
  chrome_sdk=True,
)

_grouped_config = _config(
  build_packages_in_background=True,
  chrome_sdk_build_chrome=False,
  unittests=None,
  vm_tests=[],
)

_grouped_variant_config = _grouped_config.derive(
  chrome_sdk=False,
)

_grouped_variant_release = _release.derive(_grouped_variant_config)

### Master release config.

_release.add_config('x86-mario-release',
  boards=['x86-mario'],
  master=True,
)

### Release config groups.

_config.add_group('x86-alex-release-group',
  _release.add_config('x86-alex-release',
    boards=['x86-alex'],
    critical_for_chrome=True,
  ),
  _grouped_variant_release.add_config('x86-alex_he-release',
    boards=['x86-alex_he'],
    hw_tests=[],
    upload_hw_test_artifacts=False,
    paygen_skip_testing=True,
  ),
)

_config.add_group('x86-zgb-release-group',
  _release.add_config('x86-zgb-release',
    boards=['x86-zgb'],
  ),
  _grouped_variant_release.add_config('x86-zgb_he-release',
    boards=['x86-zgb_he'],
    hw_tests=[],
    upload_hw_test_artifacts=False,
    paygen_skip_testing=True,
  ),
)

_config.add_group('parrot-release-group',
  _release.add_config('parrot-release',
    boards=['parrot'],
    afdo_use=True,
  ),
  _grouped_variant_release.add_config('parrot_ivb-release',
    boards=['parrot_ivb'],
    afdo_use=True,
  )
)

### Release AFDO configs.

release_afdo = _release.derive(
  trybot_list=False,
  hw_tests=HWTestConfig.DefaultList(pool=constants.HWTEST_CHROME_PERF_POOL,
                                    num=4) +
           HWTestConfig.AFDOList(),
  push_image=False,
  paygen=False,
  dev_installer_prebuilts=False,
)

# Now generate generic release-afdo configs if we haven't created anything more
# specific above already. release-afdo configs are builders that do AFDO profile
# collection and optimization in the same builder. Used by developers that
# want to measure performance changes caused by their changes.
def _AddAFDOConfigs():
  for board in _all_release_boards:
    if board in _x86_release_boards:
      base = {}
    else:
      base = non_testable_builder
    generate_config = _config(
        base,
        boards=(board,),
        afdo_generate_min=True,
        afdo_update_ebuild=True,
    )
    use_config = _config(
        base,
        boards=(board,),
        afdo_use=True,
    )

    config_name = '%s-%s' % (board, CONFIG_TYPE_RELEASE_AFDO)
    if config_name not in config:
      generate_config_name = '%s-%s-%s' % (board, CONFIG_TYPE_RELEASE_AFDO,
                                           'generate')
      use_config_name = '%s-%s-%s' % (board, CONFIG_TYPE_RELEASE_AFDO, 'use')
      _config.add_group(config_name,
                        release_afdo.add_config(generate_config_name,
                                                generate_config),
                        release_afdo.add_config(use_config_name, use_config))

_AddAFDOConfigs()

### Release configs.

# bayleybay-release does not enable vm_tests or unittests due to the compiler
# flags enabled for baytrail.
_release.add_config('bayleybay-release',
  boards=['bayleybay'],
  hw_tests=[],
  vm_tests=[],
  unittests=False,
)

_release.add_config('beltino-release',
  boards=['beltino'],
  hw_tests=[],
  vm_tests=[],
)

_release.add_config('fox_wtm2-release',
  boards=['fox_wtm2'],
  # Until these are configured and ready, disable them.
  signer_tests=False,
  vm_tests=[],
  hw_tests=[],
)

_release.add_config('link-release',
  boards=['link'],
  useflags=_release['useflags'] + ['highdpi'],
)

_release.add_config('link_freon-release',
  boards=['link_freon'],
  useflags=_release['useflags'] + ['highdpi'],
  hw_tests=[],
  # This build doesn't generate signed images, so don't try to release them.
  paygen=False,
  signer_tests=False,
)

_release.add_config('lumpy-release',
  boards=['lumpy'],
  critical_for_chrome=True,
  afdo_use=True,
)

# Add specific release configs for these sandybrige/ivybridge boards to
# enable AFDO. We should remove these once AFDO is enabled everywhere.
# parrot is added in parrot-release-group above.
_release.add_config('stumpy-release',
  boards=['stumpy'],
  afdo_use=True,
)

_release.add_config('butterfly-release',
  boards=['butterfly'],
  afdo_use=True,
)

_release.add_config('stout-release',
  boards=['stout'],
  afdo_use=True,
)


### Arm release configs.

_arm_release = _release.derive(non_testable_builder)

_arm_release.add_config('daisy-release',
  boards=['daisy'],
  critical_for_chrome=True,
)

# Now generate generic release configs if we haven't created anything more
# specific above already.
def _AddReleaseConfigs():
  for board in _all_release_boards:
    if board in _x86_release_boards:
      board_config = _config(
          boards=(board,),
      )
    else:
      board_config = _config(
          non_testable_builder,
          boards=(board,),
      )

    config_name = '%s-%s' % (board, CONFIG_TYPE_RELEASE)
    if config_name not in config:
      _release.add_config(config_name, board_config)

    # We have to mark all autogenerated PFQs as not important so the master
    # does not wait for them.  http://crbug.com/386214
    # If you want an important PFQ, you'll have to declare it yourself.
    pfq_config = _config(
        board_config,
        important=False,
    )

    config_name = '%s-tot-chrome-pfq-informational' % board
    if config_name not in config:
      chrome_info.add_config(config_name, pfq_config)

    config_name = '%s-chrome-pfq' % board
    if config_name not in config:
      chrome_pfq.add_config(config_name, pfq_config)

_AddReleaseConfigs()

_brillo_release = _release.derive(brillo,
  dev_installer_prebuilts=False,
)

_brillo_release.add_config('duck-release',
   boards=['duck'],

   # Hw Lab can't test, yet.
   paygen_skip_testing=True,
)

_brillo_release.add_config('gizmo-release',
   boards=['gizmo'],

   # This build doesn't generate signed images, so don't try to release them.
   paygen=False,
)

_brillo_release.add_config('panther_embedded-minimal-release',
  boards=['panther_embedded'],
  profile='minimal',
  paygen=False,
)

_arm_brillo_release = _brillo_release.derive(non_testable_builder)

_arm_brillo_release.add_config('storm-release',
   boards=['storm'],

   # Hw Lab can't test duck, yet.
   paygen_skip_testing=True,
)

_beaglebone_release = _arm_brillo_release.derive(beaglebone)

_config.add_group('beaglebone-release-group',
  _beaglebone_release.add_config('beaglebone-release',
    boards=['beaglebone'],

    # This build doesn't generate signed images, so don't try to release them.
    paygen=False,
  ),
  _beaglebone_release.add_config('beaglebone_servo-release',
    boards=['beaglebone_servo'],

    # This build doesn't generate signed images, so don't try to release them.
    paygen=False,
  ).derive(_grouped_variant_config),
)

_release.add_config('mipsel-o32-generic-release',
  brillo_non_testable,
  boards=['mipsel-o32-generic'],
  paygen_skip_delta_payloads=True,
)

_release.add_config('stumpy_moblab-release',
  moblab,
  boards=['stumpy_moblab'],
  images=['base', 'test'],
  paygen_skip_delta_payloads=True,
  # TODO: re-enable paygen testing when crbug.com/386473 is fixed.
  paygen_skip_testing=True,
)

_release.add_config('rush-release',
  boards=['rush'],
  hw_tests=[],
  # This build doesn't generate signed images, so don't try to release them.
  paygen=False,
  signer_tests=False,
)

### Per-chipset release groups

def _AddGroupConfig(name, base_board, group_boards=(),
                    group_variant_boards=(), **kwargs):
  """Generate full & release group configs."""
  for group in ('release', 'full'):
    configs = []

    all_boards = [base_board] + list(group_boards) + list(group_variant_boards)
    desc = '%s; Group config (boards: %s)' % (
        config['%s-%s' % (base_board, group)].description,
        ', '.join(all_boards))

    for board in all_boards:
      if board in group_boards:
        subconfig = _grouped_config
      elif board in group_variant_boards:
        subconfig = _grouped_variant_config
      else:
        subconfig = {}
      board_config = '%s-%s' % (board, group)
      configs.append(config[board_config].derive(subconfig, **kwargs))

    config_name = '%s-%s-group' % (name, group)
    _config.add_group(config_name, *configs, description=desc)

# pineview chipset boards
_AddGroupConfig('pineview', 'x86-mario', (
    'x86-alex',
    'x86-zgb',
), (
    'x86-alex_he',
    'x86-zgb_he',
))

# sandybridge chipset boards
_AddGroupConfig('sandybridge', 'lumpy', (
    'butterfly',
    'parrot',
    'stumpy',
), afdo_use=True)

# ivybridge chipset boards
_AddGroupConfig('ivybridge', 'stout', (), (
    'parrot_ivb',
), afdo_use=True)

# sandybridge / ivybridge chipset boards
# TODO(davidjames): Remove this once we've transitioned to separate builders for
# sandybridge / ivybridge.
_AddGroupConfig('sandybridge-ivybridge', 'lumpy', (
    'butterfly',
    'parrot',
    'stout',
    'stumpy',
), (
    'parrot_ivb',
), afdo_use=True)

# slippy-based haswell boards
# TODO(davidjames): Combine slippy and beltino into haswell canary, once we've
# optimized our builders more.
# slippy itself is deprecated in favor of the below boards, so we don't bother
# building it.
_AddGroupConfig('slippy', 'peppy', (
    'falco',
    'leon',
    'wolf',
), (
    'falco_li',
))

# beltino-based haswell boards
# beltino itself is deprecated in favor of the below boards, so we don't bother
# building it.

# TODO(dnj): Remove this once the associated Master change using -a,-b variants
# lands (#202040)
_AddGroupConfig('beltino', 'panther', (
    'monroe',
    'tricky',
    'zako',
))

_AddGroupConfig('beltino-a', 'panther', (
    'mccloud',
))

_AddGroupConfig('beltino-b', 'monroe', (
    'tricky',
    'zako',
))

# rambi-based boards
_AddGroupConfig('rambi-a', 'rambi', (
    'clapper',
    'enguarde',
    'expresso',
))

_AddGroupConfig('rambi-b', 'glimmer', (
    'gnawty',
    'kip',
    'quawks',
))

_AddGroupConfig('rambi-c', 'squawks', (
    'swanky',
    'winky',
))

# daisy-based boards
_AddGroupConfig('daisy', 'daisy', (
    'daisy_spring',
    'daisy_skate',
))

# peach-based boards
_AddGroupConfig('peach', 'peach_pit', (
    'peach_pi',
))

# nyan-based boards
_AddGroupConfig('nyan', 'nyan', (
    'nyan_big',
    'nyan_blaze',
))

# Factory and Firmware releases much inherit from these classes.  Modifications
# for these release builders should go here.

# Naming conventions also must be followed.  Factory and firmware branches must
# end in -factory or -firmware suffixes.

_factory_release = _release.derive(
  upload_hw_test_artifacts=False,
  upload_symbols=False,
  hw_tests=[],
  chrome_sdk=False,
  description='Factory Builds',
  paygen=False,
)

_firmware = _config(
  images=[],
  factory_toolkit=False,
  packages=('virtual/chromeos-firmware',),
  usepkg_setup_board=True,
  usepkg_build_packages=True,
  sync_chrome=False,
  build_tests=False,
  chrome_sdk=False,
  unittests=False,
  vm_tests=[],
  hw_tests=[],
  dev_installer_prebuilts=False,
  upload_hw_test_artifacts=False,
  upload_symbols=False,
  signer_tests=False,
  trybot_list=False,
  paygen=False,
)

_firmware_release = _release.derive(_firmware,
  description='Firmware Canary',
  manifest=constants.DEFAULT_MANIFEST,
)

_depthcharge_release = _firmware_release.derive(useflags=['depthcharge'])

_depthcharge_full_internal = full.derive(
  internal,
  _firmware,
  useflags=['depthcharge'],
  description='Firmware Informational',
)

_x86_firmware_boards = (
  'bayleybay',
  'beltino',
  'butterfly',
  'clapper',
  'enguarde',
  'expresso',
  'falco',
  'glimmer',
  'gnawty',
  'kip',
  'leon',
  'link',
  'lumpy',
  'monroe',
  'panther',
  'parrot',
  'peppy',
  'quawks',
  'rambi',
  'samus',
  'squawks',
  'stout',
  'slippy',
  'stumpy',
  'swanky',
  'winky',
  'wolf',
  'x86-mario',
  'zako',
)

_x86_depthcharge_firmware_boards = (
  'bayleybay',
  'clapper',
  'enguarde',
  'expresso',
  'glimmer',
  'gnawty',
  'kip',
  'leon',
  'link',
  'quawks',
  'rambi',
  'samus',
  'squawks',
  'swanky',
  'winky',
  'zako',
)

_arm_firmware_boards = (
  'daisy',
  'daisy_skate',
  'daisy_spring',
  'peach_pit',
  'peach_pi',
)

def _AddFirmwareConfigs():
  """Add x86 and arm firmware configs."""
  for board in _x86_firmware_boards:
    _firmware_release.add_config('%s-%s' % (board, CONFIG_TYPE_FIRMWARE),
      boards=[board],
    )

  for board in _x86_depthcharge_firmware_boards:
    _depthcharge_release.add_config(
        '%s-%s-%s' % (board, 'depthcharge', CONFIG_TYPE_FIRMWARE),
        boards=[board],
    )
    _depthcharge_full_internal.add_config(
        '%s-%s-%s-%s' % (board, 'depthcharge', CONFIG_TYPE_FULL,
                         CONFIG_TYPE_FIRMWARE),
        boards=[board],
    )

  for board in _arm_firmware_boards:
    _firmware_release.add_config('%s-%s' % (board, CONFIG_TYPE_FIRMWARE),
      non_testable_builder,
      boards=[board],
    )

_AddFirmwareConfigs()


# This is an example factory branch configuration for x86.
# Modify it to match your factory branch.
_factory_release.add_config('x86-mario-factory',
  boards=['x86-mario'],
)

# This is an example factory branch configuration for arm.
# Modify it to match your factory branch.
_factory_release.add_config('daisy-factory',
  non_testable_builder,
  boards=['daisy'],
)

_payloads = internal.derive(
  build_type=constants.PAYLOADS_TYPE,
  description='Regenerate release payloads.',
  vm_tests=[],

  # Sync to the code used to do the build the first time.
  manifest_version=True,

  # This is the actual work we want to do.
  paygen=True,

  upload_hw_test_artifacts=False,
)

def _AddPayloadConfigs():
  """Create <board>-payloads configs for all payload generating boards.

  We create a config named 'board-payloads' for every board which has a
  config with 'paygen' True. The idea is that we have a build that generates
  payloads, we need to have a tryjob to re-attempt them on failure.
  """
  payload_boards = set()

  def _search_config_and_children(search_config):
    # If paygen is enabled, add it's boards to our list of payload boards.
    if search_config['paygen']:
      for board in search_config['boards']:
        payload_boards.add(board)

    # Recurse on any child configs.
    for child in search_config['child_configs']:
      _search_config_and_children(child)

  # Search all configs for boards that generate payloads.
  for _, search_config in config.iteritems():
    _search_config_and_children(search_config)

  # Generate a payloads trybot config for every board that generates payloads.
  for board in payload_boards:
    name = '%s-payloads' % board
    _payloads.add_config(name, boards=[board])

_AddPayloadConfigs()


def GetDisplayPosition(config_name, type_order=CONFIG_TYPE_DUMP_ORDER):
  """Given a config_name, return display position specified by suffix_order.

  Args:
    config_name: Name of config to look up.
    type_order: A tuple/list of config types in the order they are to be
                displayed.

  Returns:
    If |config_name| does not contain any of the suffixes, returns the index
    position after the last element of suffix_order.
  """
  for index, config_type in enumerate(type_order):
    if config_name.endswith('-' + config_type) or config_name == config_type:
      return index

  return len(type_order)
