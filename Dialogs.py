#!/usr/bin/python

import gtk
import os, webbrowser

def url_hook(dlg, link):
	webbrowser.open(link, new=2, autoraise=1)

def email_hook(dlg, link):
	webbrowser.open(link)

gtk.about_dialog_set_url_hook(url_hook)
gtk.about_dialog_set_email_hook(email_hook)

class AboutDialog(gtk.AboutDialog):
	def __init__(self, logo=None):
		gtk.AboutDialog.__init__(self)
		self.set_properties(**{
			"name": "TDFPlayerApp_About", 
			"version": "1.0", 
			"copyright": "Copyright (c) 2009-2009 Cheng Gang", 
			"comments": "A little program that helps working with tdf.", 
			"license": "You can copy it freely.", 
			"website": "http://madge.appen.com.au/~gcheng/", 
			"authors": ["Gang Cheng gcheng@appen.com.au"], 
			"documenters": ["Gang Cheng gcheng@appen.com.au"], 
			"artists": ["Gang Cheng gcheng@appen.com.au"], 
			"translator_credits": "Gang Cheng gcheng@appen.com.au", 
			"has-separator": True, })
		if logo:
			self.set_property("logo", logo)
		self.connect("response", lambda dlg, r: dlg.hide())
# end of AboutDialog

class AudioPathDialog(gtk.Dialog):
	__gsignals__ = {
		"response": "override", 
	}
	def __init__(self, parent=None, audio_search_path=[]):
		gtk.Dialog.__init__(self, "Audio Search Path", parent, 
				gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT, 
				(gtk.STOCK_CLEAR, gtk.RESPONSE_NO, 
					gtk.STOCK_ADD, gtk.RESPONSE_YES, 
					gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE))
		self.resize(400, 300)

		self.ls_path = gtk.ListStore(str)
		self.tv_path = gtk.TreeView()

		col = gtk.TreeViewColumn("Path")
		rdr = gtk.CellRendererText()
		col.pack_start(rdr)
		col.add_attribute(rdr, "text", 0)
		self.tv_path.append_column(col)
		self.tv_path.set_property("headers-visible", False)
		self.tv_path.set_model(self.ls_path)

		label = gtk.Label("Current Search Path:")
		label.set_alignment(0.0, 0.5)
		scroll_win = gtk.ScrolledWindow()
		scroll_win.add(self.tv_path)
		scroll_win.set_shadow_type(gtk.SHADOW_IN)
		scroll_win.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)

		vbox = gtk.VBox(spacing=5)
		vbox.set_border_width(5)
		vbox.pack_start(label, expand=False)
		vbox.pack_start(scroll_win)
		vbox.show_all()
		self.vbox.pack_start(vbox)

		self.path_chooser = gtk.FileChooserDialog(
				title="Select a path", 
				parent=self, 
				action=gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER, 
				buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL, 
						gtk.STOCK_OK, gtk.RESPONSE_OK,))
		self.path_chooser.set_select_multiple(True)
		self.path_chooser.connect("response", lambda dlg, r: dlg.hide())

		self.ls_path.append(("./",))
		for path in audio_search_path: 
			self.ls_path.append((path,))

	def do_response(self, responseid):
		if responseid == gtk.RESPONSE_NO:
			self.ls_path.clear()
			self.ls_path.append(("./",))
		elif responseid == gtk.RESPONSE_YES:
			if self.path_chooser.run() == gtk.RESPONSE_OK:
				for p in self.path_chooser.get_filenames():
					self.ls_path.append((p,))
				self.path_chooser.unselect_all()
		else:
			self.hide()

	def search_audio_file(self, basename):
		iter = self.ls_path.get_iter_first()
		fullpath = ""
		while iter:
			(path,) = self.ls_path.get(iter, 0)
			fullpath = os.path.join(path, basename)
			if os.path.exists(fullpath) and os.path.isfile(fullpath):
				break
			fullpath = ""
			iter = self.ls_path.iter_next(iter)
		return fullpath
# end of AudioPathDialog

TDF_FILES_FILTER = gtk.FileFilter()
TDF_FILES_FILTER.set_name("TDF files (*.tdf)")
TDF_FILES_FILTER.add_pattern("*.tdf")
ALL_FILES_FILTER = gtk.FileFilter()
ALL_FILES_FILTER.set_name("All Files")
ALL_FILES_FILTER.add_pattern("*")

class OpenTDFDialog(gtk.FileChooserDialog):
	def __init__(self, parent=None):
		gtk.FileChooserDialog.__init__(self, 
				title="Open a TDF file", 
				parent=parent, action=gtk.FILE_CHOOSER_ACTION_OPEN, 
				buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
						gtk.STOCK_OPEN, gtk.RESPONSE_OK,))
		self.add_filter(TDF_FILES_FILTER)
		self.add_filter(ALL_FILES_FILTER)
		self.connect("response", lambda dlg, rid: dlg.hide())
# end of class OpenTDFDialog

class SaveAsTDFDialog(gtk.FileChooserDialog):
	def __init__(self, parent=None):
		gtk.FileChooserDialog.__init__(self, 
				title="Save TDF file as", 
				parent=parent, action=gtk.FILE_CHOOSER_ACTION_SAVE, 
				buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL, 
						gtk.STOCK_SAVE, gtk.RESPONSE_OK,))
		self.add_filter(TDF_FILES_FILTER)
		self.add_filter(ALL_FILES_FILTER)
		self.set_do_overwrite_confirmation(True)
		self.connect("response", lambda dlg, rid: dlg.hide())
# end of class SaveAsTDFDialog

# end of $URL$

