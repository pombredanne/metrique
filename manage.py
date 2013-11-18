#!/usr/bin/python
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4
# Author: "Chris Ward <cward@redhat.com>

'''
CLI for deploying metrique
'''

from functools import partial
import os
import sys
import virtualenv
from setuptools.sandbox import run_setup
import re


logger = virtualenv.Logger([(0, sys.stdout)])
call_subprocess = virtualenv.call_subprocess

__pkgs__ = ['metrique', 'metriqued', 'metriquec', 'metriqueu',
            'plotrique']
__src__ = 'src/'
__actions__ = ['build', 'sdist', 'install', 'develop', 'register',
               'bump', 'status']
__bumps__ = ['x', 'y', 'z', 'r']
RE_VERSION_X = re.compile(r"__version__\s+=\s+[\"']((\d+).\d+.\d+)[\"']")
RE_VERSION_Y = re.compile(r"__version__\s+=\s+[\"'](\d+.(\d+).\d+)[\"']")
RE_VERSION_Z = re.compile(r"__version__\s+=\s+[\"'](\d+.\d+.(\d+))[\"']")
RE_RELEASE = re.compile(r"__release__ = [\"']?((\d+)a?)[\"']?")


CWD = os.getcwd()
SRC_DIR = os.path.join(CWD, __src__)

USER_DIR = os.path.expanduser('~/.metrique')

# set cache dir so pip doesn't have to keep downloading over and over
PIP_CACHE = os.path.join(USER_DIR, 'pip')
PIP_EGGS = os.path.join(USER_DIR, '.python-eggs')
os.environ['PIP_DOWNLOAD_CACHE'] = PIP_CACHE

# make sure the the default user python eggs dir is secure
if not os.path.exists(PIP_EGGS):
    os.makedirs(PIP_EGGS, 0700)
else:
    os.chmod(PIP_EGGS, 0700)

expand = os.path.expanduser
makedirs = lambda x: os.makedirs(expand(x)) if not os.path.exists(x) else None

for _dir in [USER_DIR]:
    # create dirs we need, in advance
    makedirs(_dir)


def get_packages(args):
    global __pkgs__
    global SRC_DIR
    if not args.packages or 'all' in args.packages:
        return [os.path.join(SRC_DIR, pkg) for pkg in __pkgs__]
    else:
        return os.path.join(SRC_DIR, args.packages)


def call(cmd, cwd=None):
    if not cwd:
        cwd = os.getcwd()
    cmd = cmd.strip().split(' ')
    try:
        call_subprocess(cmd, cwd=cwd, show_stdout=True)
    except:
        logger.notify(str(cmd))
        raise


def extend_parser(parser):
    parser.add_option(
        '-a', '--action',
        default='install',
        choices=['install', 'develop'],
        help='setup.py action to execute')

    parser.add_option(
        '-P', '--packages',
        action='append',
        choices=__pkgs__ + ['all'],
        default=[],
        help='packages to install')

    parser.add_option(
        '-U', '--git-uri',
        default='.',
        help='git repository to use for the installation (DEFAULT: ".")')

    parser.add_option(
        '-B', '--git-branch',
        default='master',
        help='git branch to install (default: master)')

    parser.add_option(
        '--nopull',
        action='store_true',
        default=False,
        help='do not update (pull) git branch before install')

    parser.add_option(
        '--test',
        action='store_true',
        default=False,
        help='run tests after deployment completes')

    parser.add_option(
        '--ipython',
        action='store_true',
        default=False,
        help='install ipython')
virtualenv.extend_parser = extend_parser


def adjust_options(options, args):
    options.no_site_packages = True
virtualenv.adjust_options = adjust_options


def after_install(args, home_dir):
    git_uri = args.git_uri
    git_branch = args.git_branch
    pkgs = args.packages

    src_dir = os.getcwd()
    if git_uri == '.' and os.path.exists('.git'):
        # if git_uri == '.'; assume cwd is target git repo
        logger.notify('Using git repo at %s' % src_dir)
    elif not os.path.exists(src_dir):
        logger.notify('Installing %s -> %s' % (git_uri, home_dir))
        call('git clone %s %s' % (git_uri, home_dir))
        src_dir = os.path.join(home_dir, 'metrique')
    else:
        raise IOError("cwd is not a git repo! (%s)" % src_dir)

    if not args.nopull and git_uri != '.':
        call('git checkout %s' % git_branch)
        call('git pull')

    call('git --no-pager status')
    call('git --no-pager log -3')

    pip = os.path.join(home_dir, 'bin', 'pip')
    pipa = os.path.join(home_dir, 'bin', 'pip-accel')
    activate = os.path.join(home_dir, 'bin', 'activate_this.py')
    pytest = os.path.join(home_dir, 'bin', 'py.test')

    # force override existing 'activated' virt envs, if there is one
    os.environ['VIRTUAL_ENV'] = home_dir
    # activate the virtenv so all actions will be made within it
    execfile(activate, dict(__file__=activate))

    # make sure we have the installer basics and their up2date
    # argparse is needed for py2.6; pip-accel caches compiled binaries
    # first run for a new virt-env will take forever...
    # second run should be 90% faster!
    call('%s install -U pip-accel' % pip)
    call('%s install -U pip distribute setuptools' % pipa)
    call('%s install -U argparse virtualenv' % pipa)

    # this dependency is installed separately because virtenv
    # path resolution issues; fails due to being unable to find
    # the python headers in the virtenv for some reason.
    # plus, pip-accel caches the binaries, which take forever to compile
    if not pkgs == ['metriqued']:
        call('%s install -U numpy pandas' % pipa)
    # optional dependency, that's highly recommended!
    if args.ipython:
        call('%s install -U ipython' % pipa)

    install(args)

    # run py.test after install
    if args.test:
        call('%s install pytest' % pipa)
        call(pytest, cwd=src_dir)
virtualenv.after_install = after_install


def clean(args):
    # http://stackoverflow.com/a/785534/1289080
    os.system('find . -name "*.pyc" -exec rm -f {} \;')


def bump_version(regex, line, i, reset, **kwargs):
    # if we're bumping version, reset release to 1
    m = regex.match(line)
    if not m:
        raise ValueError(
            'Expected line matching __version__, got: %s' % line)
    current = m.groups()[0]
    current_parts = map(int, current.split('.'))
    if reset:
        current_parts[i] = 0
    else:
        current_parts[i] += 1
    bumped = '.'.join(map(str, current_parts))
    logger.debug('BUMP (VERSION) - %s->%s' % (current, bumped))
    return "__version__ = '%s'\n" % bumped


def bump_version_x(line, reset=False, **kwargs):
    return bump_version(RE_VERSION_X, line, 0, reset, **kwargs)


def bump_version_y(line, reset=False, **kwargs):
    return bump_version(RE_VERSION_Y, line, 1, reset, **kwargs)


def bump_version_z(line, reset=False, **kwargs):
    return bump_version(RE_VERSION_Z, line, 2, reset, **kwargs)


def bump_release(line, reset=False, ga=False):
    m = RE_RELEASE.match(line)
    if not m:
        raise ValueError(
            'Expected line matching __release__, got: %s' % line)
    current = int(m.groups()[1])
    if reset:
        bumped = 1
    else:
        bumped = current + 1  # bump by one

    if not ga:
        bumped = '"%sa"' % bumped
    else:
        # drop any 'a' if there is one
        bumped = re.sub('a$', '', str(bumped))

    logger.notify('BUMP (RELEASE): %s->%s' % (current, bumped))
    return '__release__ = %s\n' % bumped


def update_line(args, regex, bump_func):
    pkg_paths = get_packages(args)
    for path in pkg_paths:
        path = '%s/setup.py' % path
        with open(path) as setup_py:
            content = setup_py.readlines()
            for i, line in enumerate(content):
                if regex.match(line):
                    content[i] = bump_func(line)
                else:
                    continue
                break  # stop after the first replace...
        if not content:
            raise ValueError(
                "content was empty; didn't want to overwrite...")
        elif None in content:
            raise RuntimeError(
                "check your nrv strings; "
                " they're missing our regex: \n%s" % regex.pattern)
        content_str = ''.join(content)
        # write out the new setup file with bumped
        with open(path, 'w') as setup_py:
            setup_py.write(content_str)


def activate(args):
    if (hasattr(args, 'virtenv') and args.virtenv):
        activate = os.path.join(args.virtenv, 'bin', 'activate_this.py')
        execfile(activate, dict(__file__=activate))
        logger.info('Virtual Env (%s): Activated' % args.virtenv)


def setup(args, cmd, virtenv=True):
    if virtenv:
        activate(args)
    if isinstance(cmd, basestring):
        cmd = cmd.strip().split(' ')
    else:
        cmd = [s.strip() for s in cmd]
    pkg_paths = get_packages(args)
    for path in pkg_paths:
        os.chdir(path)
        sys.path.append(path)
        path = '%s/setup.py' % path
        logger.info('(%s) %s %s' % (os.getcwd(), path, str(cmd)))
        sys.argv[:] = [path] + cmd
        execfile('setup.py', {'__file__': path, '__name__': '__main__'})
        sys.path.pop()


def bump(args, kind=None, reset=False, ga=False):
    if kind is None:
        kind = 'r'
    assert kind in __bumps__
    if kind == 'x':
        regex = RE_VERSION_X
        bump(args=args, kind='y', reset=True, ga=ga)
        bump_func = partial(bump_version_x, reset=reset, ga=ga)
    elif kind == 'y':
        regex = RE_VERSION_Y
        bump(args=args, kind='z', reset=True, ga=ga)
        bump_func = partial(bump_version_y, reset=reset, ga=ga)
    elif kind == 'z':
        regex = RE_VERSION_Z
        bump(args=args, kind='r', reset=True, ga=ga)
        bump_func = partial(bump_version_z, reset=reset, ga=ga)
    elif kind == 'r':
        regex = RE_RELEASE
        bump_func = partial(bump_release, reset=reset, ga=ga)
    update_line(args, regex, bump_func)


def build(args):
    cmd = 'build'
    setup(args, cmd)


def sdist(args):
    cmd = ['sdist']
    cmd += ['upload'] if args.upload else []
    setup(args, cmd)


def install(args, cmd='install'):
    if hasattr(args, 'upload') and args.upload:
        # build and upload the current version
        sdist(args=args)
    setup(args, cmd)


def develop(args):
    cmd = 'develop'
    setup(args, cmd)


def register(args):
    cmd = 'register'
    setup(args, cmd)


def status(path):
    #[status(path=path) for path in setup_paths]
    pkg = os.path.basename(os.path.dirname(path))
    p = setup('pip show %s' % pkg)
    print p.communicate()


if __name__ == '__main__':
    import argparse

    # init cli argparser
    cli = argparse.ArgumentParser(
        description='Metrique Build CLI')

    cli.add_argument('--virtenv', type=str)
    cli.add_argument('-P', '--packages', action='append',
                     choices=__pkgs__ + ['all'], default=[])

    _sub = cli.add_subparsers(description='action')

    _deploy = _sub.add_parser('deploy')
    _deploy.add_argument('args', nargs='*')
    _deploy.set_defaults(func=virtualenv.main)

    _build = _sub.add_parser('build')
    _build.add_argument('--ga', action='store_true')
    _build.set_defaults(func=build)

    _sdist = _sub.add_parser('sdist')
    _sdist.add_argument('--ga', action='store_true')
    _sdist.add_argument('--upload', action='store_true')
    _sdist.set_defaults(func=sdist)

    _install = _sub.add_parser('install')
    _install.set_defaults(func=install)
    _develop = _sub.add_parser('develop')
    _develop.set_defaults(func=develop)
    _register = _sub.add_parser('register')
    _register.set_defaults(func=register)

    _bump = _sub.add_parser('bump')
    _bump.add_argument('--bump-kind', choices=__bumps__)
    _bump.set_defaults(func=bump)

    _status = _sub.add_parser('status')
    _status.set_defaults(func=status)

    _clean = _sub.add_parser('clean')
    _clean.set_defaults(func=clean)
    # parse argv
    args = cli.parse_args()
    try:
        args.func(args)
    except:
        # calling deploy virtualenv.main, not passing in args
        del sys.argv[1]  # pop off 'deploy' arg
        if args.packages:
            sys.argv += ['-P'] + [args.packages]
        args.func()
