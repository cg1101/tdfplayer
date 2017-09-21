#!/usr/bin/env python
# -*- coding: utf8 -*-

import os
import time
import thread
import subprocess
import socket
import logging

import gtk
import gobject
import cjson

from WavForm import WavForm
from TDFPane import TDFPane
from Dialogs import AboutDialog, AudioPathDialog, OpenTDFDialog, SaveAsTDFDialog

log = logging.getLogger(__name__)

class TDFPlayerApp:
	DEFAULT_TITLE = "TDF Player"
	ACTIONS = (
		("File!", None, "_File"), 
		("File!Open", gtk.STOCK_OPEN, "_Open...", None, "Open a file"), 
		("File!Save", gtk.STOCK_SAVE, None, None, "Save to file"), 
		("File!SaveAs", gtk.STOCK_SAVE_AS, "Save _As...", None, "Save as"), 
		("File!CheckOut", None, "Get a file", None, "Check-out a file"), 
		("File!CheckIn", None, "Submit current file", None, "Check-in current file"), 
		("File!Path", gtk.STOCK_PREFERENCES, "Audio _Path...", None, "Search audio from"), 
		("File!Quit", gtk.STOCK_QUIT, None, None, "Quit the program",), 
		("Edit!", None, "_Edit"), 
		("Help!", None, "_Help"), 
		("Help!Contents", gtk.STOCK_HELP, "_Help Contents...", None, "Get help"), 
		("Help!About", gtk.STOCK_ABOUT, "_About...", None, "About the program"), 
		("Edit!AudioPlay", gtk.STOCK_MEDIA_PLAY, "Play", None, "Play current sentence"), 
		("Edit!AudioStop", gtk.STOCK_MEDIA_STOP, "Stop", None, "Stop playing"), 
		("Edit!JoinPrev", gtk.STOCK_SORT_ASCENDING, "Join Prev", None, "Join previous sentence"), 
		("Edit!JoinNext", gtk.STOCK_SORT_DESCENDING, "Join Next", None, "Join next sentence"), 
		("Edit!Split", gtk.STOCK_CUT, "Split", None, "Split current sentence"), 
	)
	UI = """<ui>
	<menubar name="menubar1">
	  <menu action="File!">
	    <menuitem action="File!Open"/>
	    <menuitem action="File!Save"/>
	    <menuitem action="File!SaveAs"/>
		<separator/>
		<menuitem action="File!CheckOut"/>
		<menuitem action="File!CheckIn"/>
	    <separator/>
	    <menuitem action="File!Path"/>
	    <separator/>
	    <separator/>
	    <menuitem action="File!Quit"/>
	  </menu>
	  <menu action="Edit!">
	    <menuitem action="Edit!JoinPrev"/>
	    <menuitem action="Edit!JoinNext"/>
	    <menuitem action="Edit!Split"/>
	    <separator/>
	    <menuitem action="Edit!AudioPlay"/>
	    <menuitem action="Edit!AudioStop"/>
	  </menu>
	  <menu action="Help!">
	    <menuitem action="Help!Contents"/>
	    <separator/>
	    <menuitem action="Help!About"/>
	  </menu>
	</menubar>
	<toolbar name="toolbar1">
	  <toolitem action="File!Open"/>
	  <toolitem action="File!Save"/>
	  <separator/>
	  <toolitem action="Edit!JoinPrev"/>
	  <toolitem action="Edit!JoinNext"/>
	  <toolitem action="Edit!Split"/>
	  <separator/>
	  <toolitem action="Edit!AudioPlay"/>
	  <toolitem action="Edit!AudioStop"/>
	</toolbar>
	</ui>"""
	def __init__(self, audio_search_path=[], threshold=20, task=None):
		self.task = task
		self.whoami = os.getlogin()
		self.whereami = socket.gethostbyname(socket.gethostname())
		self.filetosave = None

		self.window = gtk.Window()
		self.window.set_title(self.DEFAULT_TITLE)
		self.window.resize(800, 600)
		self.window.connect("delete-event", self.quit)

		self.action_group = gtk.ActionGroup("TDFPlayerApp")
		self.action_group.add_actions(self.ACTIONS)
		for action in self.action_group.list_actions():
			action.connect("activate", self.dispatch_actions)

		uimanager = gtk.UIManager()
		uimanager.insert_action_group(self.action_group, 0)
		uimanager.add_ui_from_string(self.UI)

		menubar = uimanager.get_widget("/menubar1")
		toolbar = uimanager.get_widget("/toolbar1")
		toolbar.set_style(gtk.TOOLBAR_ICONS)

		self.aw = WavForm()
		self.aw.set_size_request(-1, 240)

		self.textview = gtk.TextView()
		self.textview.set_wrap_mode(gtk.WRAP_WORD)
		self.textview.set_size_request(-1, 80)

		scroll1 = gtk.ScrolledWindow()
		scroll1.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
		scroll1.add_with_viewport(self.textview)

		alignment = gtk.Alignment(0.5, 0.5, 0.5, 1.0)
		alignment.set_padding(5, 0, 40, 40)
		alignment.add(scroll1)

		self.tdfpane = TDFPane(threshold)
		self.tdfpane.connect("row-changing", self.on_tdf_row_changing)
		self.tdfpane.connect("row-changed", self.on_tdf_row_changed)

		vpaned = gtk.VPaned()
		vpaned.pack1(alignment, False, False)
		vpaned.pack2(self.tdfpane, True, False)
		vpaned.set_position(87)

		self.statusbar = gtk.Statusbar()

		table = gtk.Table(5, 1)
		table.attach(menubar, 0, 1, 0, 1, yoptions=0)
		table.attach(toolbar, 0, 1, 1, 2, yoptions=0)
		table.attach(self.aw, 0, 1, 2, 3, yoptions=0)
		table.attach(vpaned,  0, 1, 3, 4)
		table.attach(self.statusbar, 0, 1, 4, 5, yoptions=0)

		self.window.add(table)
		self.window.show_all()

		self.aw.grab_focus()

		if task:
			audio_search_path.extend(task.audiopath.split(":"))

		self.dlg_path  = AudioPathDialog(self.window, audio_search_path)
		self.dlg_about = AboutDialog()

		self.dlg_open = OpenTDFDialog(self.window)
		self.dlg_saveas = SaveAsTDFDialog(self.window)

		# initialize action state
		self.get_action("File!Save").set_sensitive(False)
		self.get_action("File!SaveAs").set_sensitive(False)
		self.get_action("File!CheckIn").set_sensitive(False)
		self.get_action("Edit!JoinPrev").set_sensitive(False)
		self.get_action("Edit!JoinNext").set_sensitive(False)
		self.get_action("Edit!Split").set_sensitive(False)
		self.get_action("Help!Contents").set_sensitive(False)

		self.play_info = (None, 0, 0)
		self.play_region = (0, 0)

		if task:
			self.get_action("File!Open").set_sensitive(False)
			self.get_action("File!Open").set_visible(False)
			self.get_action("File!Save").set_visible(False)
			self.get_action("File!SaveAs").set_visible(False)

			self.get_action("File!CheckOut").set_label("Get a file from task %s" % task.taskid)
		else:
			self.get_action("File!CheckOut").set_visible(False)
			self.get_action("File!CheckIn").set_visible(False)
		gobject.timeout_add(1000 * 60 * 5, self.auto_save)

	def auto_save(self):
		if self.filetosave:
			filename = self.filetosave
			try:
				self.tdfpane.save_tdf_file(filename)
			except Exception, e:
				log.error("%s" % e)
		gobject.timeout_add(1000 * 60 * 5, self.auto_save)

	def get_action(self, name):
		return self.action_group.get_action(name)

	def dispatch_actions(self, action):
		name = action.get_name()
		if name == "Help!About":
			self.dlg_about.run()
		elif name == "File!Open":
			if self.dlg_open.run() != gtk.RESPONSE_OK:
				return
			filename = self.dlg_open.get_filename()
			gobject.timeout_add(10, self.load_tdf_file, filename)
		elif name == "File!Quit":
			self.quit()
		elif name == "File!Save":
			if not self.filetosave:
				return
			filename = self.filetosave
			log.debug("try to save file as %s" % filename)
			try:
				self.tdfpane.save_tdf_file(filename)
			except Exception, e:
				log.error("%s" % e)
			else:
				if self.task:
					self.get_action("File!CheckIn").set_sensitive(True)
			#self.window.set_title(self.DEFAULT_TITLE + " - " + filename)
		elif name == "File!SaveAs":
			if self.dlg_saveas.run() != gtk.RESPONSE_OK:
				return
			filename = self.dlg_saveas.get_filename()
			## confirm overwritten
			#if os.path.exists(filename):
			#	msgbox = gtk.MessageDialog(
			#			parent=self.window, 
			#			flags=gtk.DIALOG_MODAL, 
			#			type=gtk.MESSAGE_QUESTION, 
			#			buttons=gtk.BUTTONS_YES_NO, 
			#			message_format="File already exists. Overwrite it?")
			#	msgbox.set_title("Save file")
			#	msgbox.connect("response", lambda dlg, responseid: dlg.hide())
			#	if msgbox.run() != gtk.RESPONSE_YES:
			#		return
			self.filetosave = filename
			self.get_action("File!Save").set_sensitive(True)
			self.get_action("File!Save").activate()
		elif name == "File!CheckOut":
			r = cjson.decode(self.task.checkOutAFile(self.whoami, self.whereami))
			log.debug("file check out result: %s" % repr(r))
			if r.has_key("error"):
				msgbox = gtk.MessageDialog(
						parent=self.window, 
						flags=gtk.DIALOG_MODAL, 
						type=gtk.MESSAGE_ERROR, 
						buttons=gtk.BUTTONS_OK, 
						message_format=r["error"])
				msgbox.connect("response", lambda dlg, responseid: dlg.hide())
				msgbox.run()
			else:
				filename = r["input"]
				outfile = r["output"]
				msg = r.get("message", "")
				if msg:
					if os.path.exists(outfile):
						msg = msg.title()
						msgbox = gtk.MessageDialog(
								parent=self.window, 
								flags=gtk.DIALOG_MODAL, 
								type=gtk.MESSAGE_QUESTION, 
								buttons=gtk.BUTTONS_YES_NO, 
								message_format=msg + "\nDo you want to load previously save result?")
						msgbox.connect("response", lambda dlg, responseid: dlg.hide())
						ans = msgbox.run()
						if ans == gtk.RESPONSE_YES:
							filename = outfile
				self.filetosave = outfile
				gobject.timeout_add(10, self.load_tdf_file, filename)
		elif name == "File!CheckIn":
			r = cjson.decode(self.task.checkInAFile(self.whoami))
			log.debug("file check in result: %r" % r)
			if r.has_key("error"):
				msg = r["error"].title()
				msgbox = gtk.MessageDialog(
								parent=self.window, 
								flags=gtk.DIALOG_MODAL, 
								type=gtk.MESSAGE_ERROR, 
								buttons=gtk.BUTTONS_OK, 
								message_format=msg)
				msgbox.connect("response", lambda dlg, responseid: dlg.hide())
				msgbox.run()

		elif name == "File!Path":
			self.dlg_path.run()
		elif name == "Edit!JoinNext":
			self.tdfpane.join_next(self.get_transcript())
		elif name == "Edit!JoinPrev":
			self.tdfpane.join_prev(self.get_transcript())
		elif name == "Edit!Split":
			cut_at = self.aw.get_cue_time()
			tx0, tx1 = self.get_transcript(split=True)
			self.tdfpane.split(cut_at, tx0, tx1)
		elif name == "Edit!AudioPlay":
			start, end = self.play_region
			self.aw.player.play(start, end)
		elif name == "Edit!AudioStop":
			self.aw.player.stop()

	def quit(self, *args):
		msgbox = gtk.MessageDialog( 
				parent=self.window, 
				flags=gtk.DIALOG_MODAL, 
				type=gtk.MESSAGE_QUESTION, 
				buttons=gtk.BUTTONS_YES_NO, 
				message_format="Are you sure you want to quit?")
		msgbox.set_title("Quit")
		msgbox.connect("response", lambda dlg, responseid: dlg.hide())
		if msgbox.run() == gtk.RESPONSE_YES:
			gtk.main_quit()

	def get_transcript(self, split=False):
		buf = self.textview.get_buffer()
		s_it = buf.get_start_iter()
		e_it = buf.get_end_iter()
		if split:
			iter = buf.get_iter_at_mark(buf.get_insert())
			tx0 = buf.get_text(s_it, iter)
			tx1 = buf.get_text(iter, e_it)
			tx0 = tx0.replace("\t", " ").strip()
			tx1 = tx1.replace("\t", " ").strip()
			return tx0, tx1
		else:
			transcript = buf.get_text(s_it, e_it)
			transcript = transcript.replace("\t", " ").strip()
			return transcript

	def load_tdf_file(self, filename):
		self.window.set_title(self.DEFAULT_TITLE + " - " + filename)
		try:
			count = self.tdfpane.load_tdf_file(filename)
		except Exception, e:
			log.error("%s" % e)
		if self.task:
			self.get_action("File!Save").set_visible(count > 0)
			self.get_action("File!Save").set_sensitive(count > 0)
		else:
			self.get_action("File!SaveAs").set_sensitive(count > 0)

	def play_sentence(self, reload):
		audiofile, start, end = self.play_info
		self.aw.set_selection_by_time(start, end)
		self.aw.set_viewport_by_time(start-5, end+10)
		if reload:
			thread.start_new_thread(self.reload_audio_file, (audiofile,))
		self.aw.player.stop()
		time.sleep(0.5)
		self.aw.player.play(start, end)
		return False

	def reload_audio_file(self, audiofile):
		log.debug("loading %s" % audiofile)
		self.aw.set_media_file(audiofile)

	def on_tdf_row_changing(self, tdfpane, row):
		if row:
			row["transcript"] = self.get_transcript()

	def on_tdf_row_changed(self, tdfpane, row, has_prev, has_next):
		basename = row.get("file", "")
		start = row.get("start", 0)
		end = row.get("end", 0)
		tx = row.get("transcript", "")

		self.play_region = (start, end)
		self.textview.get_buffer().set_text(tx)
		self.get_action("Edit!JoinPrev").set_sensitive(has_prev)
		self.get_action("Edit!JoinNext").set_sensitive(has_next)
		if not basename:
			self.get_action("Edit!AudioPlay").set_sensitive(False)
			self.get_action("Edit!AudioStop").set_sensitive(False)
			return
		self.get_action("Edit!Split").set_sensitive(True)
		audiofile = self.dlg_path.search_audio_file(basename)
		if not audiofile:
			self.get_action("Edit!AudioPlay").set_sensitive(False)
			self.get_action("Edit!AudioStop").set_sensitive(False)
			pass
		else:
			self.get_action("Edit!AudioPlay").set_sensitive(True)
			self.get_action("Edit!AudioStop").set_sensitive(True)
			reload = audiofile != self.play_info[0]
			self.play_info = (audiofile, start, end)
			gobject.timeout_add(100, self.play_sentence, reload)

# end of TDFPlayerApp

# end of $URL$

