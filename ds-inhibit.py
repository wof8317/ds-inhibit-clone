#!/usr/bin/python
# SPDX-License-Identifier: BSD-2-Clause
# vim:ts=4:sw=4:et
#
# Copyright (c) 2022 Valve Software
# Maintainer: Vicki Pfau <vi@endrift.com>
import glob
import logging
import os
import pyinotify
import re
import time

logger = logging.getLogger(__name__)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(levelname)s: %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)


class Inhibitor:
    @classmethod
    def get_nodes(cls, id: int) -> list[str]:
        devs = glob.glob(f'/sys/class/hidraw/hidraw{id}/device/input/input*')
        return [f'{d}/inhibited' for d in devs if glob.glob(f'{d}/mouse*')]

    @classmethod
    def can_inhibit(cls, id: int) -> bool:
        logger.debug(f'Checking if hidraw{id} can be inhibited')
        driver = os.readlink(f'/sys/class/hidraw/hidraw{id}/device/driver').split('/')
        if driver[-1] not in ('sony', 'playstation'):
            logger.debug(f'Not a PlayStation controller')
            return False
        nodes = cls.get_nodes(id)
        if not nodes:
            logger.debug(f'No nodes to inhibit')
            return False
        for node in nodes:
            if not os.access(node, os.W_OK):
                logger.debug(f'Node {node} cannot be inhibited')
                return False
            logger.debug(f'Node {node} can be inhibited')
        return True

    @classmethod
    def inhibit(cls, id: int):
        for node in cls.get_nodes(id):
            with open(node, 'w') as f:
                f.write('1\n')

    @classmethod
    def uninhibit(cls, id: int):
        for node in cls.get_nodes(id):
            with open(node, 'w') as f:
                f.write('0\n')


class InhibitionServer:
    MATCH = re.compile(r'^/dev/hidraw(\d+)$')

    def __init__(self):
        self.running = False

    def watch(self, hidraw):
        match = self.MATCH.match(hidraw)
        if not match:
            logger.debug(f'New node {hidraw} is not a hidraw')
            return
        if not Inhibitor.can_inhibit(match.group(1)):
            return
        logger.info(f'Adding {hidraw} to watchlist')
        self._inotify.add_watch(hidraw, pyinotify.IN_DELETE_SELF |
                                pyinotify.IN_OPEN |
                                pyinotify.IN_CLOSE_NOWRITE |
                                pyinotify.IN_CLOSE_WRITE,
                                proc_fun=self._hidraw_process)
        self._check(hidraw)

    def _start(self):
        logger.info('Starting server')
        self._inotify = pyinotify.WatchManager()
        self._inotify.add_watch('/dev', pyinotify.IN_CREATE,
                                proc_fun=self._node_added)
        for hidraw in glob.glob('/dev/hidraw*'):
            self.watch(hidraw)
        self.running = True

    def _stop(self):
        logger.info('Stopping server')
        for watch in self._inotify.watches.values():
            match = self.MATCH.match(watch.path)
            if not match:
                continue
            Inhibitor.uninhibit(match.group(1))

    def _node_added(self, ev):
        logger.debug(f'New device {ev.pathname} found')
        time.sleep(0.25)  # Wait a quarter second for nodes to enumerate
        self.watch(ev.pathname)

    def _hidraw_process(self, ev):
        if ev.mask & pyinotify.IN_DELETE_SELF:
            logger.debug(f'Device {ev.path} removed')
            self._inotify.del_watch(ev.wd)
            return
        self._check(ev.path)

    def _check(self, hidraw: str):
        open_procs = []
        match = self.MATCH.match(hidraw)
        if not match:
            return
        for proc in os.listdir('/proc'):
            if not proc.isnumeric():
                continue
            if not os.access(f'/proc/{proc}/fd', os.R_OK):
                continue
            for fd in os.listdir(f'/proc/{proc}/fd'):
                try:
                    path = os.readlink(f'/proc/{proc}/fd/{fd}')
                except FileNotFoundError:
                    continue
                if not path or path != hidraw:
                    continue
                open_procs.append(proc)
        steam = False
        for proc in open_procs:
            with open(f'/proc/{proc}/comm') as f:
                procname = f.read()
            if not procname:
                continue
            if procname.rstrip() == 'steam':
                steam = True
        if steam:
            logger.info(f'Inhibiting {hidraw}')
            Inhibitor.inhibit(match.group(1))
        else:
            logger.info(f'Uninhibiting {hidraw}')
            Inhibitor.uninhibit(match.group(1))

    def poll(self):
        notifier = pyinotify.Notifier(self._inotify)
        notifier.loop()

    def serve(self):
        self._start()

        try:
            self.poll()
        except (KeyboardInterrupt, OSError):
            pass

        self._stop()


if __name__ == '__main__':
    logger.setLevel(logging.INFO)
    server = InhibitionServer()
    server.serve()
