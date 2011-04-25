#!/usr/bin/python
#
# Copyright (c) 2011 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for main.py."""

import doctest
import optparse
import os
import re
import unittest

import chromite.lib.cros_build_lib as cros_lib
from chromite.lib import text_menu
from chromite.shell import main
from chromite.shell import utils
import mox


# Allow protected access, since we are closely partnered with the
# code that we're testing...
#
# pylint: disable=W0212

# Needed to make pylint not yell so much about mocked out stuff
# (it yells about AndReturn, MultipleTimes, ...).
#
# TODO(dianders): Any better solution than this heavy hammer?
#
# pylint: disable=E1101, E1103

# Just being a unittest.TestCase gives us 14 public methods.  Unless we
# disable this, we can only have 6 tests in a TestCase.  That's not enough.
#
# pylint: disable=R0904


class _DeathException(Exception):
  """A bogus exception used by the mock out of cros_lib.Die."""
  pass


class TestFindSpec(unittest.TestCase):
  """Test utils.FindSpec."""

  def setUp(self):
    """Test initialization."""
    # Create our mox and stub out function calls used by _FindSpec()...
    self.mox = mox.Mox()
    self.mox.StubOutWithMock(os, 'listdir')
    self.mox.StubOutWithMock(os.path, 'isfile')
    self.mox.StubOutWithMock(cros_lib, 'Die')
    self.mox.StubOutWithMock(text_menu, 'TextMenu')

  def tearDown(self):
    """Test cleanup."""
    # Unset stubs...
    self.mox.UnsetStubs()

  def testInvalidSpec(self):
    """Test that _FindSpec('bogusSpec') causes cros_lib.Die()."""
    # Pass this spec name...
    spec_name = 'bogusSpec'

    # We'll tell mox to say that these specs exist...
    dir_list = ['x87-toadstool.spec', 'x87-luigi.SPeC', 'x88-princess.spec',
                '_default']

    # This spec doesn't represent any full path.
    os.path.isfile(spec_name).AndReturn(False)

    # This spec isn't found in our search path.
    os.path.isfile(mox.Regex('^/.*%s.spec$' % spec_name)).MultipleTimes(
        ).AndReturn(False)

    # Give the fake directory listing...
    os.listdir(mox.IsA(basestring)).MultipleTimes().AndReturn(dir_list)

    # Should be a call to cros_lib.Die.  We'll have it fake a _DeathException...
    cros_lib.Die(mox.IsA(basestring)).AndRaise(_DeathException)

    # Run the command and verify proper mocks were called...
    self.mox.ReplayAll()
    self.assertRaises(_DeathException, utils.FindSpec, 'bogusSpec')
    self.mox.VerifyAll()

  def testFullPath(self):
    """Test that _FindSpec(full_path) returns full_path.

    _FindSpec is defined so that if you pass a full file path to it, it
    should just return that.  It doesn't need to have any special suffix or
    live in a spec folder.
    """
    # Pass this spec name...
    spec_name = __file__

    # Just say that this is a full path...
    os.path.isfile(spec_name).AndReturn(True)

    # Run the command and verify proper mocks were called...
    self.mox.ReplayAll()
    path = utils.FindSpec(spec_name)
    self.mox.VerifyAll()

    self.assertEqual(path, spec_name,
                     '_FindSpec() should just return param if full path.')

  def testExactSpecName(self):
    """Test that _FindSpec(exact_spec_name) returns the path for the spec."""
    # We'll search for this bogus spec; we'll use mox to pretend it exists in
    # the search path.
    spec_name = 'y87-luigi'

    # This spec doesn't represent any full path
    os.path.isfile(spec_name).AndReturn(False)

    # When we look through the search path for this spec (with .spec at
    # the end), we will consider the spec to be found.
    os.path.isfile(mox.Regex('^/.*%s.spec$' % spec_name)).AndReturn(True)

    # Run the command and verify proper mocks were called...
    self.mox.ReplayAll()
    spec_path = utils.FindSpec(spec_name)
    self.mox.VerifyAll()

    self.assertTrue(re.search('^/.*%s.spec$' % spec_name, spec_path),
                    '_FindSpec() should have returned absolute path for spec.')

  def testUniqueSpecName(self):
    """Test that _FindSpec(unique_part_name) returns the path for the spec."""
    # We'll search for this spec.  Weird capitalization on purpose to test
    # case sensitiveness.
    spec_name = 'ToaDSTooL'

    # We'll tell mox to say that these specs exist in the first directory...
    dir_list = ['_default',
                'x87-luigi.spec', 'x87-toadstool.SPeC', 'x88-princess.spec']

    # We expect it to find this spec.
    expected_result = 'x87-toadstool.SPeC'

    # Self-checks for test code...
    assert dir_list == sorted(dir_list)

    # This spec doesn't represent any full path.
    os.path.isfile(spec_name).AndReturn(False)

    # This spec isn't found in our search path.
    os.path.isfile(mox.Regex('^/.*%s.spec$' % spec_name)).MultipleTimes(
        ).AndReturn(False)

    # Return our directory listing.
    # TODO(dianders): How to make first mocked call return dir_list and
    # subsequent return []
    os.listdir(mox.IsA(basestring)).AndReturn(dir_list)

    os.path.isfile(mox.Regex('^/.*%s$' % expected_result)).AndReturn(True)

    # Run the command and verify proper mocks were called...
    self.mox.ReplayAll()
    spec_path = utils.FindSpec(spec_name)
    self.mox.VerifyAll()

    self.assertTrue(re.search('^/.*%s$' % expected_result, spec_path),
                    '_FindSpec("%s") incorrectly returned "%s".' %
                    (spec_name, spec_path))

  def _TestBlankSpecName(self, menu_return):
    """Helper for tests passing a blank spec name.

    Args:
      menu_return: This value is returned by TextMenu.  Could be none or an
          integer index into the dir_list of this function.
    """
    # We'll search for this spec.
    spec_name = ''

    # We'll tell mox to say that these specs exist in the first directory...
    # ...only valid specs to make it easier to compare things.
    dir_list = ['x87-luigi.spec', 'x87-toadstool.SPeC', 'x88-princess.spec']
    num_specs = len(dir_list)

    # Self-checks for test code...
    assert menu_return < len(dir_list)
    assert dir_list == sorted(dir_list)

    # This spec doesn't represent any full path.
    os.path.isfile(spec_name).AndReturn(False)

    # Return our directory listing.
    # TODO(dianders): How to make first mocked call return dir_list and
    # subsequent return []
    os.listdir(mox.IsA(basestring)).AndReturn(dir_list)

    for i in xrange(num_specs):
      os.path.isfile(mox.Regex('^/.*%s$' % dir_list[i])).AndReturn(True)

    # We expect there to be 1 more item than we passed in, since we account
    # for 'HOST'.
    check_num_items_fn = lambda items: len(items) == (num_specs + 1)

    # Add 1 to menu_return, since 'HOST' is first...
    if menu_return is None:
      adjusted_menu_return = menu_return
    else:
      adjusted_menu_return = menu_return + 1

    # Should be one call to TextMenu, which will return menu_return.
    text_menu.TextMenu(mox.And(mox.IsA(list), mox.Func(check_num_items_fn)),
                       mox.IsA(basestring)).AndReturn(adjusted_menu_return)

    # Should die in response to the quit if directed to quit.
    if menu_return is None:
      cros_lib.Die(mox.IsA(basestring)).AndRaise(_DeathException)

    # Run the command and verify proper mocks were called...
    self.mox.ReplayAll()
    if menu_return is None:
      self.assertRaises(_DeathException, utils.FindSpec, spec_name)
    else:
      spec_path = utils.FindSpec(spec_name)
    self.mox.VerifyAll()

    if menu_return is not None:
      expected_result = dir_list[menu_return]
      self.assertTrue(re.search('^/.*%s$' % expected_result, spec_path),
                      '_FindSpec("%s") incorrectly returned "%s".' %
                      (spec_name, spec_path))

  def testBlankSpecNameWithQuit(self):
    """Test that _FindSpec('') shows menu, mocking quit."""
    self._TestBlankSpecName(None)

  def testBlankSpecNameWithChoice0(self):
    """Test that _FindSpec('') shows menu, mocking choice 0."""
    self._TestBlankSpecName(0)

  def testPartialSpecNameWithChoice0(self):
    """Test that _FindSpec(non_unique_str) shows menu, mocking choice 0."""
    # We'll search for this spec.
    spec_name = 'x87'

    # We'll tell mox to say that these specs exist in the first directory...
    dir_list = ['_default',
                'x87-luigi.spec', 'x87-toadstool.SPeC', 'x88-princess.spec']

    # We expect 2 matches and should get back luigi as choice 0.
    matches = ['x87-luigi.spec', 'x87-toadstool.SPeC']
    num_match = len(matches)
    expected_result = 'x87-luigi.spec'

    # Self-checks for test code...
    assert dir_list == sorted(dir_list)

    # This spec doesn't represent any full path.
    os.path.isfile(spec_name).AndReturn(False)

    # This spec isn't found in our search path.
    os.path.isfile(mox.Regex('^/.*%s.spec$' % spec_name)).MultipleTimes(
        ).AndReturn(False)

    # Return our directory listing.
    # TODO(dianders): How to make first mocked call return dir_list and
    # subsequent return []
    os.listdir(mox.IsA(basestring)).AndReturn(dir_list)

    for i in xrange(num_match):
      os.path.isfile(mox.Regex('^/.*%s$' % matches[i])).AndReturn(True)

    # Should be one call to TextMenu, which will return 0.
    text_menu.TextMenu(mox.And(mox.IsA(list),
                               mox.Func(lambda items: len(items) == num_match)),
                       mox.IsA(basestring)).AndReturn(0)

    # Run the command and verify proper mocks were called...
    self.mox.ReplayAll()
    spec_path = utils.FindSpec(spec_name)
    self.mox.VerifyAll()

    self.assertTrue(re.search('^/.*%s$' % expected_result, spec_path),
                    '_FindSpec("%s") incorrectly returned "%s".' %
                    (spec_name, spec_path))

class TestParseArguments(unittest.TestCase):
  """Test main._ParseArguments."""

  def setUp(self):
    """Test initialization."""
    self.parser = optparse.OptionParser()

    # Verbose defaults to full for now, just to keep people acclimatized to
    # vast amounts of comforting output.
    self.parser.add_option('-v', dest='verbose', default=3, type='int',
        help='Control verbosity: 0=silent, 1=progress, 3=full')
    self.parser.add_option('-q', action='store_const', dest='verbose', const=0,
        help='Be quieter (sets verbosity to 1)')

  def testEmpty(self):
    options, cmd, sub = main._ParseArguments(self.parser,
        [])
    self.assertEqual(options.verbose, 3)
    self.assertEqual(cmd, '')
    self.assertEqual(sub, [])

  def testBadOption(self):
    self.assertRaises(SystemExit, main._ParseArguments, self.parser,
        ['chromite', '--bad'])
    self.assertRaises(SystemExit, main._ParseArguments, self.parser,
        ['chromite', '--bad', 'build'])

  def testSubcmd(self):
    options, cmd, sub = main._ParseArguments(self.parser,
        ['chromite', 'build'])
    self.assertEqual(options.verbose, 3)
    self.assertEqual(cmd, 'build')
    self.assertEqual(sub, [])

  def testSubcmdQuiet(self):
    options, cmd, sub = main._ParseArguments(self.parser,
        ['chromite', '-q', 'build'])
    self.assertEqual(options.verbose, 0)
    self.assertEqual(cmd, 'build')
    self.assertEqual(sub, [])

  def testSubcmdVerbose2(self):
    options, cmd, sub = main._ParseArguments(self.parser,
        ['chromite', '-v2', 'build'])
    self.assertEqual(options.verbose, 2)
    self.assertEqual(cmd, 'build')
    self.assertEqual(sub, [])

  def testSubcmdVerbose4(self):
    options, cmd, sub = main._ParseArguments(self.parser,
        ['chromite', '-v', '4', 'build'])
    self.assertEqual(options.verbose, 4)
    self.assertEqual(cmd, 'build')
    self.assertEqual(sub, [])

  def testSubcmdArgs(self):
    options, cmd, sub = main._ParseArguments(self.parser,
        ['chromite', '-v', '4', 'build', 'seaboard', '--clean'])
    self.assertEqual(options.verbose, 4)
    self.assertEqual(cmd, 'build')
    self.assertEqual(sub, ['seaboard', '--clean'])

if __name__ == '__main__':
  doctest.testmod(main)
  unittest.main()
