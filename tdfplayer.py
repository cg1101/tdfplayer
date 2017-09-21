#!/usr/bin/env python
# -*- coding: utf8 -*-

import sys
import os
import getopt
import logging

import pygtk
pygtk.require("2.0")
import gtk, gtk.glade

import pygst
pygst.require("0.10")
import gst

from db import getTask
from TDFPlayerApp import TDFPlayerApp

if __name__ == "__main__":
	logging.basicConfig(format="%(name)s %(message)s", level=logging.DEBUG)
	try:
		opts, args = getopt.gnu_getopt(sys.argv[1:], "", 
				["audio-search-path=", "threshold=", "taskID="])
	except getopt.GetoptError, e:
		print >>sys.stderr, e
		sys.exit(2)

	audio_search_path = []
	threshold = 20
	taskID = None
	for o, a in opts:
		if o in ("--audio-search-path"):
			audio_search_path.extend(a.split(":"))
		elif o in ("--threshold"):
			threshold = int(a)
		elif o in ("--taskID"):
			taskID = int(a)
	task = None
	if taskID:
		task = getTask(taskID)
		if not task:
			print >>sys.stderr, "task %s not configured" % taskID
			sys.exit(1)

	scptpath = sys.argv[0]
	while os.path.islink(scptpath):
		scptpath = os.path.realpath(scptpath)
	scptdir = os.path.dirname(scptpath)
	logo = os.path.join(scptdir, "logo.png")
	try:
		gtk.window_set_default_icon_from_file(logo)
		gtk.gdk.threads_init()
		TDFPlayerApp(audio_search_path, threshold, task)
		gtk.main()
	except KeyboardInterrupt:
		pass

# end of $URL$

