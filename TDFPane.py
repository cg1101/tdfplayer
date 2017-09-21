#!/usr/bin/env python

import os
import thread
import logging

import gobject
import gtk
import pango

log = logging.getLogger(__name__)

TDF_COLUMNS = (
	("file", str), 
	("channel", int), 
	("start", float), 
	("end", float), 
	("speaker", str), 
	("speakerType", str), 
	("speakerDialect", str), 
	("transcript", str), 
	("section", str), 
	("turn", str), 
	("segment", str), 
	("sectionType", str), 
	("suType", str), 
	("speakerRole", str), 
)
SORT_COLUMN_ID = len(TDF_COLUMNS)
FLAG_COLUMN_ID = SORT_COLUMN_ID + 1
SORT_KEY_FORMAT = "%s_%09.3f_%09.3f"

FLAG_JOINED  = 0x1
FLAG_CUT     = 0x2
FLAG_OVERLAP = 0x4

OVERLAP_THRESHOLD = 1
###KB OVERLAP_THRESHOLD = 2

KEY_COLUMN_NAMES = ("file", "start", "end", "transcript")
KEY_COLUMN_IDS = (0, 2, 3, 7)

class TDFPane(gtk.VBox):
	__gsignals__ = {
		"row-changing": (
			gobject.SIGNAL_RUN_LAST, 
			gobject.TYPE_NONE, 
			(gobject.TYPE_PYOBJECT,), 
		), 
		"row-changed": (
			gobject.SIGNAL_RUN_LAST, 
			gobject.TYPE_NONE, 
			(gobject.TYPE_PYOBJECT, gobject.TYPE_BOOLEAN, gobject.TYPE_BOOLEAN), 
		), 
	}
	def __init__(self, threshold=20):
		gtk.VBox.__init__(self)
		self.threshold = threshold
		self.tv_tdf = gtk.TreeView()
		scroll2 = gtk.ScrolledWindow()
		scroll2.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
		scroll2.add_with_viewport(self.tv_tdf)
		self.pack_start(scroll2)

		col_types = [t[1] for t in TDF_COLUMNS]
		col_types.append(str) # append sort key column
		col_types.append(int) # append falgs column

		self.ls_raw = gtk.ListStore(*col_types)
		self.ls_raw.set_sort_column_id(SORT_COLUMN_ID, gtk.SORT_ASCENDING)
		self.ls_raw.set_default_sort_func(lambda model, it1, it2:
				cmp(model.get(it1, 0, 2, 3), model.get(it2, 0, 2, 3)))

		col_headers = [t[0] for t in TDF_COLUMNS]
		for i, hdr in enumerate(col_headers):
			col = gtk.TreeViewColumn(hdr)
			col.set_alignment(0.5)
			col.set_min_width(5)
			col.set_resizable(True)
			rdr = gtk.CellRendererText()
			if hdr == "transcript":
				rdr.set_property("ellipsize", pango.ELLIPSIZE_END)
				col.set_expand(True)
			#	col.set_max_width(1000)
			#	rdr.set_property("editable", True)
			#	rdr.set_property("wrap-mode", gtk.WRAP_WORD)
			#	col.connect("notify::width", self.on_tx_column_resized, rdr)
			col.pack_start(rdr)
			col.set_cell_data_func(rdr, self.cell_data_func, i)
			self.tv_tdf.append_column(col)
		#col = gtk.TreeViewColumn("")
		#col.set_max_width(20)
		#col.set_min_width(20)
		#rdr = gtk.CellRendererPixbuf()
		#col.pack_start(rdr)
		#col.set_cell_data_func(rdr, self.on_cell_data_enquired)
		#self.tdf_widget.insert_column(col, 0)
		col = gtk.TreeViewColumn("")
		col.set_expand(False)
		self.tv_tdf.append_column(col)
		self.tv_tdf.set_model(self.ls_raw)
		self.tv_tdf.get_selection().connect("changed", self.on_tdf_row_changed)

		self.it_curr = None
		self.it_prev = None
		self.it_prev = None
		self.row_buf = {}

		self.overlap_marker_id = -1

	def on_tdf_row_changed(self, selobj):
		row = {}
		if self.it_curr:
			row.update(self.row_buf)
		self.emit("row-changing", row)

	def do_row_changing(self, row):
		if self.it_curr:
			if self.row_buf["transcript"] != row["transcript"]:
				self.ls_raw.set(self.it_curr, 7, row["transcript"])
		self.post_row_changing()
	
	def post_row_changing(self):
		m, it = self.tv_tdf.get_selection().get_selected()
		if not it:
			self.it_curr = None
			self.it_prev = None
			self.it_next = None
			self.row_buf = {}
			self.emit("row-changed", {}, False, False)
			return

		self.it_curr = it
		self.row_buf = dict(zip(KEY_COLUMN_NAMES, m.get(self.it_curr, *KEY_COLUMN_IDS)))
		curr_basename, curr_channel = m.get(self.it_curr, 0, 1)
		curr_start, curr_end, curr_tx = m.get(self.it_curr, 2, 3, 7)

		# find previous candidate
		self.it_prev = None
		model = gtk.TreeModelSort(m)
		model.set_sort_column_id(SORT_COLUMN_ID, gtk.SORT_DESCENDING)
		desc_it = model.convert_child_iter_to_iter(None, it)
		desc_it = model.iter_next(desc_it)
		while desc_it:
			prev_basename, prev_channel = model.get(desc_it, 0, 1)
			if prev_basename != curr_basename:
				break
			elif prev_channel == curr_channel:
				self.it_prev = model.convert_iter_to_child_iter(None, desc_it)
				break
			desc_it = model.iter_next(desc_it)

		# find next candidate
		self.it_next = None
		asc_it = m.iter_next(it)
		while asc_it:
			next_basename, next_channel = m.get(asc_it, 0, 1)
			if next_basename != curr_basename:
				break
			elif next_channel == curr_channel:
				self.it_next = asc_it
				break
			asc_it = m.iter_next(asc_it)

		row = {}
		row.update(self.row_buf)
		self.emit("row-changed", row, bool(self.it_prev), bool(self.it_next))

	def cell_data_func(self, tvcol, cellrdr, model, it, col_i):
		value = model.get_value(it, col_i)
		flags = model.get_value(it, FLAG_COLUMN_ID)
		channel, start, end = model.get(it, 1, 2, 3)
		treemodel, curriter = self.tv_tdf.get_selection().get_selected()
		if curriter and treemodel.get_path(curriter) == model.get_path(it):
			cellrdr.set_property("weight", 800)
		else:
			cellrdr.set_property("weight", 400)
		if col_i != 7:
			cellrdr.set_property("foreground", "black")
		elif channel % 2 == 0:
			cellrdr.set_property("foreground", "darkgreen")
		else:
			cellrdr.set_property("foreground", "darkred")
		if col_i in (2, 3):
			cellrdr.set_property("text", "%.3f" % value)
		else:
			cellrdr.set_property("text", "%s" % value)
		if flags & FLAG_OVERLAP:
			cellrdr.set_property("background", "pink")
		elif end - start >= self.threshold:
			cellrdr.set_property("background", "lightblue")
		else:
			cellrdr.set_property("background", "white")

	def load_tdf_file(self, filename):
		f = open(filename)
		buf = []
		errors = []
		line_no = 0
		for l in f:
			line_no += 1
			if l.startswith("file"): continue
			try:
				l = unicode(l.rstrip("\r\n"), "utf-8")
				r = l.split("\t")
				r[1] = int(r[1])
				r[2] = float(r[2])
				r[3] = float(r[3])
				if (r[3] - r[2]) <= 0:
					raise ValueError, "end time stamp is less than start"
				r.append(SORT_KEY_FORMAT % (r[0], r[2], r[3]))
				r.append(0)
				buf.append(tuple(r))
			except Exception, e:
				log.debug("%s" % e)
				log.debug("%s" % l)
				errors.append(str(line_no))
				continue
		f.close()
		#buf.sort(cmp=lambda r1, r2: cmp(r1[SORT_COLUMN_ID], r2[SORT_COLUMN_ID]))
		self.ls_raw.clear()

		if errors:
			msgbox = gtk.MessageDialog(
				parent=self.get_ancestor(gtk.Window), 
				flags=gtk.DIALOG_MODAL, 
				type=gtk.MESSAGE_ERROR, 
				buttons=gtk.BUTTONS_OK, 
				message_format="tdf file contains error "
					"in following lines:\n%s" % (", ".join(errors))
			)
			msgbox.set_title("Error")
			msgbox.connect("response", lambda dlg, responseid: dlg.hide())
			msgbox.run()
			return 0

		for r in buf:
			self.ls_raw.append(r)
		self.overlap_marker_id = thread.start_new_thread(self.mark_overlaps, ())
		return len(self.ls_raw)

	def save_tdf_file(self, filename):
		log.debug("saving %s" % filename)
		fdir = os.path.dirname(filename)
		if not os.path.exists(fdir):
			os.makedirs(fdir)
		f = open(filename, "w")
		m = self.ls_raw
		iter = m.get_iter_first()
		while iter:
			r = list(m.get(iter, *range(SORT_COLUMN_ID)))
			r[1] = "%d" % r[1]
			r[2] = "%.3f" % r[2]
			r[3] = "%.3f" % r[3]
			f.write(("\t".join(["%s" % x for x in r])).encode("utf-8") + "\n")
			iter = m.iter_next(iter)
		f.close()

	def join_prev(self, transcript):
		it = self.it_curr
		it_prev = self.it_prev
		m = self.ls_raw
		if not it or not it_prev:
			return
		start1, tx1, flags = m.get(it_prev, 2, 7, FLAG_COLUMN_ID)
		basename, end = m.get(it, 0, 3)
		newtx = " ".join([tx1, transcript])
		m.set_value(it_prev, 3, end)
		m.set_value(it_prev, 7, newtx)
		m.set_value(it_prev, SORT_COLUMN_ID, SORT_KEY_FORMAT % (basename, start1, end))
		m.set_value(it_prev, FLAG_COLUMN_ID, flags | FLAG_JOINED)
		m.remove(it)
		selobj = self.tv_tdf.get_selection()
		selobj.select_iter(it_prev)
		self.overlap_marker_id = thread.start_new_thread(self.mark_overlaps, ())

	def join_next(self, transcript):
		it = self.it_curr
		it_next = self.it_next
		m = self.ls_raw
		if not it or not it_next:
			return
		end1, tx1 = m.get(it_next, 3, 7)
		basename, start, flags = m.get(it, 0, 2, FLAG_COLUMN_ID)
		newtx = " ".join([transcript, tx1])
		m.set_value(it, 3, end1)
		m.set_value(it, 7, newtx)
		m.set_value(it, SORT_COLUMN_ID, SORT_KEY_FORMAT % (basename, start, end1))
		m.set_value(it, FLAG_COLUMN_ID, flags | FLAG_JOINED)
		m.remove(it_next)
		self.post_row_changing()
		self.on_tdf_row_changed(self.tv_tdf.get_selection())
		self.overlap_marker_id = thread.start_new_thread(self.mark_overlaps, ())

	def split(self, cut_at, tx0, tx1):
		selobj = self.tv_tdf.get_selection()
		m, it = selobj.get_selected()
		if not it:
			return
		row = list(m.get(it, *range(FLAG_COLUMN_ID+1)))
		if cut_at <= row[2] or cut_at >= row[3]:
			#return
			pass
		m.set_value(it, 3, cut_at)
		m.set_value(it, SORT_COLUMN_ID, SORT_KEY_FORMAT % (row[0], row[2], cut_at))
		m.set_value(it, 7, tx0)
		m.set_value(it, FLAG_COLUMN_ID, row[FLAG_COLUMN_ID] | FLAG_CUT)
		row[2] = cut_at
		row[7] = tx1
		row[SORT_COLUMN_ID] = SORT_KEY_FORMAT % (row[0], row[2], row[3])
		row[FLAG_COLUMN_ID] = 0 | FLAG_CUT
		m.insert_after(it, row)
		self.post_row_changing()
		self.overlap_marker_id = thread.start_new_thread(self.mark_overlaps, ())

	def mark_overlaps(self):
		my_id = self.overlap_marker_id
		# 1st pass, clear overlap flag in all lines
		it0 = self.ls_raw.get_iter_first()
		while my_id == self.overlap_marker_id and it0:
			flag0 = self.ls_raw.get_value(it0, FLAG_COLUMN_ID)
			self.ls_raw.set_value(it0, FLAG_COLUMN_ID, flag0 & ~FLAG_OVERLAP)
			it0 = self.ls_raw.iter_next(it0)
		# 2nd pass, test and set overlap flag
		it0 = self.ls_raw.get_iter_first()
		while my_id == self.overlap_marker_id and it0:
			af0, chnl0, start0, end0, flag0 = self.ls_raw.get(it0, 0, 1, 2, 3, FLAG_COLUMN_ID)
			it1 = self.ls_raw.iter_next(it0)
			while it1:
				af1, chnl1, start1, end1, flag1 = self.ls_raw.get(it1, 0, 1, 2, 3, FLAG_COLUMN_ID)
				overlap = False
				if af0 == af1 and end0 > start1:
					if end0 >= end1:
						length = end1 - start1
					else:
						length = end0 - start1
					if length >= OVERLAP_THRESHOLD or chnl0 == chnl1:
						overlap = True
				if overlap:
					self.ls_raw.set_value(it0, FLAG_COLUMN_ID, flag0 | FLAG_OVERLAP)
					self.ls_raw.set_value(it1, FLAG_COLUMN_ID, flag1 | FLAG_OVERLAP)
					it1 = self.ls_raw.iter_next(it1)
				else:
					break
			it0 = self.ls_raw.iter_next(it0)
		self.tv_tdf.queue_draw()
# end of TDFPane

# end of $URL$

