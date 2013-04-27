#!/usr/bin/env python

""" Entry point of the console application.

    Contains the argument parser and CLI interaction. """

import traceback
import readline
import argparse
import logging
import os.path
import getpass
import pprint
import shlex
import sys
import csv

import pol.safe
import pol.passgen
import pol.terminal
import pol.humanize
import pol.clipboard
import pol.progressbar

class Program(object):
    def parse_args(self, argv):
        # Common
        parser = argparse.ArgumentParser(add_help=False)
        g_basic = parser.add_argument_group('basic options')
        g_basic.add_argument('--safe', '-s', type=str, default='~/.pol',
                            metavar='PATH',
                    help='Path to safe')
        g_basic.add_argument('-h', '--help', action='help',
                    help='show this help message and exit')
        g_basic.add_argument('--verbose', '-v', action='count',
                            dest='verbosity',
                    help='Add these to make pol chatty')
        g_advanced = parser.add_argument_group('advanced options')
        g_advanced.add_argument('--workers', '-w', type=int, metavar='N',
                    help='Number of workers processes (/threads)')
        g_advanced.add_argument('--threads', '-t', action='store_true',
                    help='Use worker threads instead of processes')
        g_advanced.add_argument('--profile', '-p', action='store_true',
                    help='Profile performance of main process')
        subparsers = parser.add_subparsers(title='commands')

        # pol init
        p_init = subparsers.add_parser('init', add_help=False,
                    help='Create a new safe')
        p_init_b = p_init.add_argument_group('basic options')
        p_init_b.add_argument('-h', '--help', action='help',
                    help='show this help message and exit')
        p_init_b.add_argument('--force', '-f', action='store_true',
                    help='Remove any existing safe')
        p_init_a = p_init.add_argument_group('advanced options')
        p_init_a.add_argument('--rerand-bits', '-R', type=int, default=1025,
                    help='Minimal size in bits of prime used for '+
                            'rerandomization')
        p_init_a.add_argument('--precomputed-group-parameters', '-P',
                        action='store_true', dest='precomputed_gp',
                    help='Use precomputed group parameters for rerandomization')
        p_init_a.add_argument('--passwords', '-p', nargs='+', metavar='PW',
                    help='Passwords for containers as normally input '+
                            'interactively')
        p_init_a.add_argument('--i-know-its-unsafe', action='store_true',
                    help='Required for obviously unsafe actions')
        p_init.set_defaults(func=self.cmd_init)

        # pol list
        p_list = subparsers.add_parser('list', add_help=False,
                    help='List entries')
        p_list_b = p_list.add_argument_group('basic options')
        p_list_b.add_argument('-h', '--help', action='help',
                    help='show this help message and exit')
        p_list_a = p_list.add_argument_group('basic options')
        p_list_a.add_argument('--password', '-p', metavar='PASSWORD',
                    help='Password of container to list')
        p_list.set_defaults(func=self.cmd_list)

        # pol generate
        p_generate = subparsers.add_parser('generate', add_help=False,
                    help='Generates and stores a password')
        p_generate.add_argument('key')
        p_generate_b = p_generate.add_argument_group('basic options')
        p_generate_b.add_argument('-h', '--help', action='help',
                    help='show this help message and exit')
        p_generate_b.add_argument('--note', '-n')
        p_generate_b.add_argument('--no-copy', '-N', action='store_true',
                    help='Do not copy secret to clipboard.')
        p_generate_a = p_generate.add_argument_group('advanced options')
        p_generate_a.add_argument('--password', '-p', metavar='PASSWORD',
                    help='Password of container to add password to')
        p_generate.set_defaults(func=self.cmd_generate)

        # pol paste
        p_paste = subparsers.add_parser('paste', add_help=False,
                    help='Stores a secret from the clipboard')
        p_paste.add_argument('key')
        p_paste_b = p_paste.add_argument_group('basic options')
        p_paste_b.add_argument('-h', '--help', action='help',
                    help='show this help message and exit')
        p_paste_b.add_argument('--note', '-n')
        p_paste_a = p_paste.add_argument_group('advanced options')
        p_paste_a.add_argument('--password', '-p', metavar='PASSWORD',
                    help='Password of container to add secret to')
        p_paste.set_defaults(func=self.cmd_paste)

        # pol copy
        p_copy = subparsers.add_parser('copy', add_help=False,
                    help='Copies a password to the clipboard')
        p_copy.add_argument('key')
        p_copy_b = p_copy.add_argument_group('basic options')
        p_copy_b.add_argument('-h', '--help', action='help',
                    help='show this help message and exit')
        p_copy_a = p_copy.add_argument_group('advanced options')
        p_copy_a.add_argument('--password', '-p', metavar='PASSWORD',
                    help='Password of container to copy secret from')
        p_copy.set_defaults(func=self.cmd_copy)

        # pol put
        p_put = subparsers.add_parser('put', add_help=False,
                    help='Stores a secret')
        p_put.add_argument('key')
        p_put_b = p_put.add_argument_group('basic options')
        p_put_b.add_argument('-h', '--help', action='help',
                    help='show this help message and exit')
        p_put_b.add_argument('--note', '-n')
        p_put_b.add_argument('--secret', '-s',
                    help='The secret to store.  If none is specified, reads '+
                         'secret from stdin.')
        p_put_a = p_put.add_argument_group('advanced options')
        p_put_a.add_argument('--password', '-p', metavar='PASSWORD',
                    help='Password of container to add secret to')
        p_put.set_defaults(func=self.cmd_put)

        # pol get
        p_get = subparsers.add_parser('get', add_help=False,
                    help='Write secret to stdout')
        p_get.add_argument('key')
        p_get_b = p_get.add_argument_group('basic options')
        p_get_b.add_argument('-h', '--help', action='help',
                    help='show this help message and exit')
        p_get_a = p_get.add_argument_group('advanced options')
        p_get_a.add_argument('--password', '-p', metavar='PASSWORD',
                    help='Password of container to get secret from')
        p_get.set_defaults(func=self.cmd_get)

        # pol touch
        p_touch = subparsers.add_parser('touch', add_help=False,
                    help='Rerandomizes blocks')
        p_touch_b = p_touch.add_argument_group('basic options')
        p_touch_b.add_argument('-h', '--help', action='help',
                    help='show this help message and exit')
        p_touch.set_defaults(func=self.cmd_touch)

        # pol raw
        p_raw = subparsers.add_parser('raw', add_help=False,
                    help='Shows raw data of safe')
        p_raw.add_argument('-h', '--help', action='help',
                    help='show this help message and exit')
        p_raw.add_argument('--blocks', '-b', action='store_true',
                    help='Also print raw blocks')
        p_raw.add_argument('--passwords', '-p', nargs='+', metavar='PW',
                    help='Also show data of containers opened by '+
                            'these passwords')
        p_raw.set_defaults(func=self.cmd_raw)

        # pol import-psafe3
        p_import_psafe3 = subparsers.add_parser('import-psafe3', add_help=False,
                    help='Imports entries from a psafe3 db')
        p_import_psafe3.add_argument('path',
                    help='Path to psafe3 database')
        p_import_psafe3_b = p_import_psafe3.add_argument_group(
                                    'basic options')
        p_import_psafe3_b.add_argument('-h', '--help', action='help',
                    help='show this help message and exit')
        p_import_psafe3_a = p_import_psafe3.add_argument_group(
                                    'advanced options')
        p_import_psafe3.add_argument('--password', '-p', metavar='PASSWORD',
                    help='Password of container to import to')
        p_import_psafe3.add_argument('--psafe3-password', '-P',
                    metavar='PASSWORD',
                    help='Password of psafe3 db to import')
        p_import_psafe3.set_defaults(func=self.cmd_import_psafe3)

        # pol import-keepass
        p_import_keepass = subparsers.add_parser('import-keepass',
                        add_help=False,
                    help='Imports entries from a KeePass 1.x db')
        p_import_keepass.add_argument('path',
                    help='Path to KeePass database')
        p_import_keepass_b = p_import_keepass.add_argument_group(
                                    'basic options')
        p_import_keepass_b.add_argument('-h', '--help', action='help',
                    help='show this help message and exit')
        p_import_keepass_b.add_argument('-K', '--keepass-keyfile',
                            metavar='PATH',
                    help='Keyfile used to open KeePass database')
        p_import_keepass_a = p_import_keepass.add_argument_group(
                                    'advanced options')
        p_import_keepass_a.add_argument('--password', '-p', metavar='PASSWORD',
                    help='Password of container to import to')
        p_import_keepass_a.add_argument('--keepass-password', '-P',
                    metavar='PASSWORD',
                    help='Password of KeePass db to import')
        p_import_keepass.set_defaults(func=self.cmd_import_keepass)

        # pol export
        p_export = subparsers.add_parser('export',
                        add_help=False,
                    help='Exports entries to CSV')
        p_export.add_argument('--output', '-o',
                    help='Path to CSV file to write to.  Defaults to stdout.',
                    default='-')
        p_export_b = p_export.add_argument_group('basic options')
        p_export_b.add_argument('-h', '--help', action='help',
                    help='show this help message and exit')
        p_export_b.add_argument('-f', '--force', action='store_true',
                    help='Overwrite existing file')
        p_export_a = p_export.add_argument_group('advanced options')
        p_export_a.add_argument('--password', '-p', metavar='PASSWORD',
                    help='Password of container to export')
        p_export.set_defaults(func=self.cmd_export)

        # pol shell
        p_shell = subparsers.add_parser('shell',
                        add_help=False,
                    help='Start interactive shell')
        p_shell_b = p_shell.add_argument_group(
                                    'basic options')
        p_shell_b.add_argument('-h', '--help', action='help',
                    help='show this help message and exit')
        p_shell.set_defaults(func=self.cmd_shell)

        # pol speed
        p_speed = subparsers.add_parser('speed',
                        add_help=False,
                    help='Measures speed of the components of pol')
        p_speed_b = p_speed.add_argument_group(
                                    'basic options')
        p_speed_b.add_argument('-h', '--help', action='help',
                    help='show this help message and exit')
        p_speed.set_defaults(func=self.cmd_speed)

        self.args = parser.parse_args(argv)

    def main(self, argv):
        try:
            if not argv:
                argv = ['shell']

            # Parse arguments
            self.parse_args(argv)

            # Set up logging
            extra_logging_config = {}
            if self.args.verbosity >= 2:
                level = logging.DEBUG
                extra_logging_config['format'] = ('%(relativeCreated)d '+
                        '%(levelname)s %(name)s %(message)s')
            elif self.args.verbosity == 1:
                level = logging.INFO
            else:
                level = logging.WARNING
            logging.basicConfig(level=level, **extra_logging_config)

            # Profile?
            if self.args.profile:
                import yappi
                yappi.start()

            # Execute command
            ret = self._run_command()
            if self.args.profile:
                yappi.stop()
                yappi.print_stats()

            return ret
        except Exception:
            self._handle_uncaught_exception()

    def cmd_init(self):
        if (os.path.exists(os.path.expanduser(self.args.safe))
                and not self.args.force):
            print '%s exists.  Use -f to override.' % self.args.safe
            return -10
        if self.args.rerand_bits < 1025 and not self.args.i_know_its_unsafe:
            print 'You should now use less than 1025b group parameters.'
            return -9
        if self.args.precomputed_gp and not self.args.i_know_its_unsafe:
            # TODO are 2049 precomputed group parameters safe?
            print 'You should now use precomputed group parameters.'
            return -9
        if self.args.passwords:
            interactive = False
            cmdline_pws = list(reversed(self.args.passwords))
        else:
            interactive = True
        if interactive:
            print "You are about to create a new safe.  A safe can have up to six"
            print "separate containers to store your secrets.  A container is"
            print "accessed by one of its passwords.  Without one of its passwords,"
            print "you cannot prove the existence of a container."
            print
        first = True
        second = False
        pws = []
        for i in xrange(1, 7):
            if interactive:
                if not first:
                    print
                print 'Container #%s' % i
                if first:
                    print "  Each container must have a master-password.  This password gives"
                    print "  full access to the container."
                    print
                if second:
                    print "  Now enter the passwords for the second container."
                    print "  Leave blank if you do not want a second container."
                    print
            if interactive:
                if first:
                    masterpw = pol.terminal.zxcvbn_getpass(
                            'Enter master-password: ', '    ')
                else:
                    masterpw = pol.terminal.zxcvbn_getpass(
                            'Enter master-password [stop]: ', '    ')
            else:
                masterpw = cmdline_pws.pop() if cmdline_pws else ''
            if not first and not masterpw:
                    break
            if interactive and first:
                print
                print "  A container can have a list-password.  With this password you can"
                print "  list and add entries.  You cannot see the secrets of the existing"
                print "  entries.  Leave blank if you do not want a list-password."
                print
            if interactive:
                listpw = pol.terminal.zxcvbn_getpass(
                            'Enter list-password [no list-password]: ', '    ')
            else:
                listpw = cmdline_pws.pop() if cmdline_pws else ''
            if interactive and first:
                print
                print "  A container can have an append-password.  With this password you"
                print "  can only add entries.  You cannot see the existing entries."
                print "  Leave blank if you do not want an append-passowrd."
                print
            if interactive:
                appendpw = pol.terminal.zxcvbn_getpass(
                        'Enter append-password [no append-password]: ', '    ')
            else:
                appendpw = cmdline_pws.pop() if cmdline_pws else ''
            if second:
                second = False
            if first:
                first = False
                second = True
            pws.append((masterpw if masterpw else None,
                        listpw if listpw else None,
                        appendpw if appendpw else None))
        if interactive:
            print
        if not self.args.precomputed_gp:
            print 'Generating group parameters for this safe. This can take a while ...'
        # TODO generate group parameters in parallel
        progressbar = pol.progressbar.ProbablisticProgressBar()
        progressbar.start()
        def progress(step, x):
            if step == 'p' and x is None:
                progressbar.start()
            elif step == 'p' and x:
                progressbar(x)
            elif step == 'g':
                progressbar.end()
        try:
            with pol.safe.create(os.path.expanduser(self.args.safe),
                                 override=self.args.force,
                                 nworkers=self.args.workers,
                                 gp_bits=self.args.rerand_bits,
                                 progress=progress,
                                 precomputed_gp=self.args.precomputed_gp,
                                 use_threads=self.args.threads) as safe:
                for i, mlapw in enumerate(pws):
                    mpw, lpw, apw = mlapw
                    print '  allocating container #%s ...' % (i+1)
                    c = safe.new_container(mpw, lpw, apw)
                print '  trashing freespace ...'
                safe.trash_freespace()
        except pol.safe.SafeAlreadyExistsError:
            print '%s exists.  Use -f to override.' % self.args.safe
            return -10
    
    def cmd_touch(self):
        with self._open_safe() as safe:
            safe.touch()

    def cmd_raw(self):
        with self._open_safe() as safe:
            d = dict(safe.data)
            if not self.args.blocks:
                del d['blocks']
            pprint.pprint(d)
            if not self.args.passwords:
                return
            for password in self.args.passwords:
                for container in safe.open_containers(password,
                        on_move_append_entries=self._on_move_append_entries):
                    print
                    print 'Container %s' % container.id
                    if container.main_data:
                        pprint.pprint(container.main_data)
                    if container.append_data:
                        pprint.pprint(container.append_data)
                    if container.secret_data:
                        pprint.pprint(container.secret_data)

    def cmd_get(self):
        with self._open_safe() as safe:
            found_one = False
            entries = []
            for container in safe.open_containers(
                    self.args.password if self.args.password
                            else getpass.getpass('Enter password: '),
                        on_move_append_entries=self._on_move_append_entries):
                if not found_one:
                    found_one = True
                try:
                    for entry in container.get(self.args.key):
                        if len(entry) == 3:
                            entries.append((container, entry))
                except pol.safe.MissingKey:
                    continue
                except KeyError:
                    continue
            if not found_one:
                sys.stderr.write('The password did not open any container.\n')
                return -1
            if not entries:
                sys.stderr.write('No entries found.\n')
                return -4
            if len(entries) > 1:
                sys.stderr.write("Multiple entries found.\n")
                return -8
            entry = entries[0][1]
            sys.stderr.write(' note: %s\n' % repr(entry[1]))
            print entry[2]
            return

    def cmd_copy(self):
        if not pol.clipboard.available:
            print 'Clipboard access not available.'
            print 'Use `pol get\' to print secrets.'
            return -7
        with self._open_safe() as safe:
            found_one = False
            entries = []
            for container in safe.open_containers(
                    self.args.password if self.args.password
                            else getpass.getpass('Enter password: '),
                        on_move_append_entries=self._on_move_append_entries):
                if not found_one:
                    found_one = True
                try:
                    for entry in container.get(self.args.key):
                        if len(entry) == 3:
                            entries.append((container, entry))
                except pol.safe.MissingKey:
                    continue
                except KeyError:
                    continue
            if not found_one:
                print 'The password did not open any container.'
                return -1
            if not entries:
                print 'No entries found'
                return -4
            if len(entries) == 1:
                entry = entries[0][1]
                print ' note: %s' % repr(entry[1])
                print 'Copied secret to clipboard.  Press any key to clear ...'
                pol.clipboard.copy(entry[2])
                pol.terminal.wait_for_keypress()
                pol.clipboard.clear()
                return
            print '%s entries found.' % len(entries)
            print
            first = True
            for i, tmp in enumerate(entries):
                if first:
                    first = False
                else:
                    print
                container, entry = tmp
                print 'Entry #%s from container @%s' % (i+1, container.id)
                print ' note: %s' % repr(entry[1])
                print 'Copied secret to clipboard.  Press any key to clear ...'
                pol.clipboard.copy(entry[2])
                pol.terminal.wait_for_keypress()
                pol.clipboard.clear()
    def cmd_paste(self):
        if not pol.clipboard.available:
            print 'Clipboard access not available.'
            print 'Use `pol put\' to add passwords from stdin.'
            return -7
        pw = pol.clipboard.paste()
        if not pw:
            print 'Clipboard is empty'
            return -3
        return self._store(pw)
        pol.clipboard.clear()
    def cmd_put(self):
        pw = self.args.secret if self.args.secret else sys.stdin.read()
        if not pw:
            print 'No secret given'
            return -3
        return self._store(pw)
    def _store(self, pw):
        with self._open_safe() as safe:
            found_one = False
            stored = False
            for container in safe.open_containers(
                    self.args.password if self.args.password
                            else getpass.getpass('Enter (append-)password: '),
                        on_move_append_entries=self._on_move_append_entries):
                if not found_one:
                    found_one = True
                try:
                    container.add(self.args.key, self.args.note, pw)
                    container.save()
                    stored = True
                    break
                except pol.safe.MissingKey:
                    pass
            if not found_one:
                print 'The password did not open any container.'
                return -1
            if found_one and not stored:
                print 'No append access to the containers opened by this password'
                return -2
    def cmd_generate(self):
        pw = pol.passgen.generate_password()
        found_one = False
        stored = False
        with self._open_safe() as safe:
            for container in safe.open_containers(
                    self.args.password if self.args.password
                            else getpass.getpass('Enter (append-)password: '),
                        on_move_append_entries=self._on_move_append_entries):
                if not found_one:
                    found_one = True
                try:
                    container.add(self.args.key, self.args.note, pw)
                    container.save()
                    stored = True
                    break
                except pol.safe.MissingKey:
                    pass
            if not found_one:
                print 'The password did not open any container.'
                return -1
            if found_one and not stored:
                print 'No append access to the containers opened by this password'
                return -2
            if not pol.clipboard.available:
                print 'Password stored.  Clipboard access not available.'
                print 'Use `pol get\' to show password'
                return
            if self.args.no_copy:
                return
            pol.clipboard.copy(pw)
            print 'Copied password to clipboard.  Press any key to clear ...'
            pol.terminal.wait_for_keypress()
            pol.clipboard.clear()
            # TODO do rerandomization in parallel

    def cmd_list(self):
        with self._open_safe() as safe:
            found_one = False
            for container in safe.open_containers(
                    self.args.password if self.args.password
                            else getpass.getpass('Enter (list-)password: '),
                        on_move_append_entries=self._on_move_append_entries):
                if not found_one:
                    found_one = True
                else:
                    print
                print 'Container @%s' % container.id
                try:
                    got_entry = False
                    for key, note in container.list():
                        got_entry = True
                        print ' %-20s %s' % (key, repr(note) if note else '')
                    if not got_entry:
                        print '  (empty)'
                except pol.safe.MissingKey:
                    print '  (no list access)'
            if not found_one:
                print ' No containers found'

    def cmd_import_keepass(self):
        # First load keepass db
        import pol.importers.keepass
        kppwd = (self.args.keepass_password if self.args.keepass_password
                        else getpass.getpass('Enter password for KeePass db: '))
        fkeyfile = None
        if self.args.keepass_keyfile:
            fkeyfile = open(self.args.keepass_keyfile)
        try:
            with open(self.args.path) as f:
                groups, entries = pol.importers.keepass.load(f, kppwd, fkeyfile)
        finally:
            if fkeyfile:
                fkeyfile.close()

        # Secondly, find a container
        with self._open_safe() as safe:
            found_one = False
            the_container = None
            for container in safe.open_containers(
                    self.args.password if self.args.password
                            else getpass.getpass('Enter (append-)password: '),
                        on_move_append_entries=self._on_move_append_entries):
                if not found_one:
                    found_one = True
                if container.can_add:
                    the_container = container
                    break
            if not found_one:
                print 'The password did not open any container.'
                return -1
            if not the_container:
                print ('No append access to the containers opened '+
                            'by this password')
                return -2

            # Import the entries
            n_imported = 0
            for entry in entries:
                if not entry['uuid'].int:
                    continue
                notes = []
                n_imported += 1
                if 'notes' in entry and entry['notes']:
                    notes.append(entry['notes'])
                if 'username' in entry and entry['username']:
                    notes.append('user: '+entry['username'])
                if 'url' in entry and entry['url']:
                    notes.append('url: '+entry['url'])
                the_container.add(entry['title'],
                                  '\n'.join(notes),
                                  entry['password'])
            the_container.save()
            print "%s entries imported" % n_imported

    def cmd_import_psafe3(self):
        # First load psafe3 db
        import pol.importers.psafe3
        ps3pwd = (self.args.psafe3_password if self.args.psafe3_password
                        else getpass.getpass('Enter password for psafe3 db: '))
        with open(self.args.path) as f:
            header, records = pol.importers.psafe3.load(f, ps3pwd)

        # Secondly, find a container
        with self._open_safe() as safe:
            found_one = False
            the_container = None
            for container in safe.open_containers(
                    self.args.password if self.args.password
                            else getpass.getpass('Enter (append-)password: '),
                        on_move_append_entries=self._on_move_append_entries):
                if not found_one:
                    found_one = True
                if container.can_add:
                    the_container = container
                    break
            if not found_one:
                print 'The password did not open any container.'
                return -1
            if not the_container:
                print ('No append access to the containers opened '+
                            'by this password')
                return -2

            # Import the records
            for record in records:
                notes = []
                if 'notes' in record and record['notes']:
                    notes.append(record['notes'])
                if 'email-address' in record and record['email-address']:
                    notes.append('email: '+record['email-address'])
                if 'username' in record and record['username']:
                    notes.append('user: '+record['username'])
                if 'url' in record and record['url']:
                    notes.append('url: '+record['url'])
                the_container.add(record['title'],
                                  '\n'.join(notes),
                                  record['password'])
            the_container.save()
            print "%s records imported" % len(records)

    def cmd_speed(self):
        import pol.speed
        return pol.speed.main(self)

    def cmd_shell(self):
        # TODO a more stateful shell would be nice: then we only have to
        #       ask for the password and rerandomize once.
        if not os.path.exists(os.path.expanduser(self.args.safe)):
            print "No safe found.  Type `init' to create a new safe."
        while True:
            try:
                line = raw_input('pol> ').strip()
            except EOFError:
                break
            except KeyboardInterrupt:
                sys.stderr.write("\nUse C-d to quit.\n")
                continue
            if not line:
                continue
            argv = shlex.split(line)
            try:
                self.parse_args(argv)
            except SystemExit:
                continue
            if self.args.func == self.cmd_shell:
                continue
            self._run_command()

    def cmd_export(self):
        close_f = False
        rows_written = 0
        found_one = False
        try:
            if self.args.output == '-':
                f = sys.stdout
            else:
                if os.path.exists(self.args.output) and not self.args.force:
                    sys.stderr.write("%s exists. Use -f to override.\n"
                                            % self.args.output)
                    return -11
                f = open(self.args.output, 'w')
                close_f = True
            writer = csv.writer(f)
            with self._open_safe() as safe:
                for container in safe.open_containers(
                        self.args.password if self.args.password
                                else getpass.getpass('Enter password: '),
                            on_move_append_entries=self._on_move_append_entries):
                    found_one = True
                    for entry in container.list(with_secrets=True):
                        rows_written += 1
                        writer.writerow(entry)
            if not found_one:
                sys.stderr.write("The password did not open any container.\n")
                return -1
        finally:
            if close_f:
                f.close()
        sys.stderr.write("%s entries exported.\n" % rows_written)

    def _rerand_progress(self):
        progressbar = pol.progressbar.ProgressBar()
        started = False
        def progress(v):
            if not started:
                progressbar.start()
            progressbar(v)
            if v == 1.0:
                progressbar.end()
        return progress
    def _on_move_append_entries(self, entries):
        sys.stderr.write("  moved entries into container: %s\n" % (
                pol.humanize.join([entry[0] for entry in entries])))
    def _open_safe(self):
        return pol.safe.open(os.path.expanduser(self.args.safe),
                           nworkers=self.args.workers,
                           use_threads=self.args.threads,
                           progress=self._rerand_progress())
    def _run_command(self):
        try:
            return self.args.func()
        except pol.safe.SafeNotFoundError:
            sys.stderr.write("%s: no such file.\n" % self.args.safe)
            sys.stderr.write("To create a new safe, run `pol init'.\n")
            return -5
        except pol.safe.SafeLocked:
            sys.stderr.write("%s: locked.\n" % self.args.safe)
            # TODO add a `pol break-lock'
            return -6
        except pol.safe.WrongMagicError:
            sys.stderr.write("%s: not a pol safe.\n" % self.args.safe)
            return -13
        except KeyboardInterrupt:
            sys.stderr.write("\n^C\n")
            return -14
        except Exception:
            self._handle_uncaught_exception()
            return -12
    def _handle_uncaught_exception(self):
        sys.stderr.write("\n")
        sys.stderr.write("An unhandled exception occured:\n")
        sys.stderr.write("\n   ")
        sys.stderr.write(traceback.format_exc().replace("\n", "\n   "))
        sys.stderr.write("\n")
        sys.stderr.write("Please report this error:\n")
        sys.stderr.write("\n")
        sys.stderr.write("   https://github.com/bwesterb/pol/issues\n")
        sys.stderr.write("\n")
        sys.stderr.flush()


def entrypoint(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    return Program().main(argv)

if __name__ == '__main__':
    sys.exit(entrypoint())
