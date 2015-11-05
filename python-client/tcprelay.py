#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
#   tcprelay.py - TCP connection relay for usbmuxd
#
#   * now ported to python 3
#
# Copyright (C) 2009    Hector Martin "marcan" <hector@marcansoft.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 or version 3.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301  USA

import usbmux
import socketserver
import select
from argparse import ArgumentParser
import sys
import threading

class SocketRelay(object):
    def __init__(self, a, b, maxbuf=65535):
        self.a = a
        self.b = b
        self.atob = b""
        self.btoa = b""
        self.maxbuf = maxbuf
    def handle(self):
        while True:
            rlist = []
            wlist = []
            xlist = [self.a, self.b]
            if self.atob:
                wlist.append(self.b)
            if self.btoa:
                wlist.append(self.a)
            if len(self.atob) < self.maxbuf:
                rlist.append(self.a)
            if len(self.btoa) < self.maxbuf:
                rlist.append(self.b)
            rlo, wlo, xlo = select.select(rlist, wlist, xlist)
            if xlo:
                return
            if self.a in wlo:
                n = self.a.send(self.btoa)
                self.btoa = self.btoa[n:]
            if self.b in wlo:
                n = self.b.send(self.atob)
                self.atob = self.atob[n:]
            if self.a in rlo:
                s = self.a.recv(self.maxbuf - len(self.atob))
                if not s:
                    return
                self.atob += s
            if self.b in rlo:
                s = self.b.recv(self.maxbuf - len(self.btoa))
                if not s:
                    return
                self.btoa += s
            #print("Relay iter: %8d atob, %8d btoa, lists: %r %r %r"%(len(self.atob), len(self.btoa), rlo, wlo, xlo))

class TCPRelay(socketserver.BaseRequestHandler):
    def handle(self):
        print("Incoming connection to %d"%self.server.server_address[1])
        mux = usbmux.USBMux(args.sockpath)
        print("Waiting for devices...")
        if not mux.devices:
            mux.process(1.0)
        if not mux.devices:
            print("No device found")
            self.request.close()
            return
        dev = mux.devices[0]
        print("Connecting to device %s"%str(dev))
        dsock = mux.connect(dev, self.server.rport)
        lsock = self.request
        print("Connection established, relaying data")
        try:
            fwd = SocketRelay(dsock, lsock, self.server.bufsize * 1024)
            fwd.handle()
        finally:
            dsock.close()
            lsock.close()
        print("Connection closed")

class TCPServer(socketserver.TCPServer):
    allow_reuse_address = True

class ThreadedTCPServer(socketserver.ThreadingMixIn, TCPServer):
    pass

parser = ArgumentParser() #usage="usage: %prog [OPTIONS] RemotePort[:LocalPort] [RemotePort[:LocalPort]]...")
parser.add_argument("-t", "--threaded", dest='threaded', action='store_true', default=False, help="use threading to handle multiple connections at once")
parser.add_argument("-i", "--ipaddr", dest='ip', metavar='IPADDRESS', type=str, default='localhost', help="specify the local IP to bind TCP sockets to")
parser.add_argument("-b", "--bufsize", dest='bufsize', action='store', metavar='KILOBYTES', type=int, default=128, help="specify buffer size for socket forwarding")
parser.add_argument("-s", "--socket", dest='sockpath', action='store', metavar='PATH', type=str, default=None, help="specify the path of the usbmuxd socket")
parser.add_argument('port_forwardings', metavar='RemotePort[:LocalPort]', type=str, nargs='+', help="set port forwardings")

args = parser.parse_args()

HOST = args.ip
serverclass = TCPServer
if args.threaded:
    serverclass = ThreadedTCPServer

ports = []

for arg in args.port_forwardings:
    try:
        if ':' in arg:
            rport, lport = arg.split(":")
            rport = int(rport)
            lport = int(lport)
            ports.append((rport, lport))
        else:
            ports.append((int(arg), int(arg)))
    except:
        parser.print_help()
        sys.exit(1)

servers=[]

for rport, lport in ports:
    print("Forwarding local port %d to remote port %d on ip %s"%(lport, rport, HOST))
    server = serverclass((HOST, lport), TCPRelay)
    server.rport = rport
    server.bufsize = args.bufsize
    servers.append(server)

alive = True

while alive:
    try:
        rl, wl, xl = select.select(servers, [], [])
        for server in rl:
            server.handle_request()
    except:
        alive = False
