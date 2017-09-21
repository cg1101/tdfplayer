#!/usr/bin/python

import os, errno
import thread, time, math
import array
import gobject
import gtk
import pango
import gst

from Metrics import Metrics
from SampleLoader import SampleLoader
from Player import Player

class WavForm(gtk.Widget):
	DEFAULT_PALETTE = {
		"chnl_in":   gtk.gdk.color_parse("darkblue"), 
		"chnl_out":  gtk.gdk.color_parse("black"), 
		"odd_in":    gtk.gdk.color_parse("green"), 
		"odd_out":   gtk.gdk.color_parse("darkgreen"), 
		"even_in":   gtk.gdk.color_parse("red"), 
		"even_out":  gtk.gdk.color_parse("darkred"), 
		"boundary":  gtk.gdk.color_parse("cyan"), 
		"grid":      gtk.gdk.color_parse("darkgray"), 
		"tick":      gtk.gdk.color_parse("lightgray"), 
		"center":    gtk.gdk.color_parse("lightgray"), 
	}
	VIEWPORT_ZOOM_IN   = 0
	VIEWPORT_ZOOM_OUT  = 1
	VIEWPORT_PAN_LEFT  = 2
	VIEWPORT_PAN_RIGHT = 3
	#__gproperties__ = {}
	__gsignals__ = {
		"sample-data-changed": (
			gobject.SIGNAL_RUN_LAST, 
			gobject.TYPE_NONE, 
			()
		), 
		"audio-format-changed": (
			gobject.SIGNAL_RUN_FIRST, 
			gobject.TYPE_NONE, 
			(gobject.TYPE_PYOBJECT, gobject.TYPE_INT)
		), 
	}
	def __init__(self, adjustment=None):
		gtk.Widget.__init__(self)
		self.set_flags(gtk.CAN_FOCUS)

		self.offscreen_pixmap = None
		self.palette = {}
		self.gc = {}

		self.cursor = gtk.gdk.Cursor(gtk.gdk.CROSS)

		context = self.create_pango_context()
		desc = context.get_font_description()
		desc.set_family("monospace")
		desc.set_absolute_size(12 * pango.SCALE)
		self.layout12 = pango.Layout(context)
		desc.set_absolute_size(10 * pango.SCALE)
		self.layout10 = pango.Layout(context)
		desc.set_absolute_size(9  * pango.SCALE)
		self.layout9  = pango.Layout(context)

		self.metrics = Metrics(self.layout10)

		self.adjustment = None
		self.handler_id_changed = -1
		self.handler_id_value_changed = -1

		self.player = Player(self)

		self.audiofile = ""
		self.caps = None
		self.data = array.array("b")
		self.loader_thread_id = -1
		self.fr_cut_in = 0
		self.fr_cut_out = 8000*60
		self.x_cue_pos = -1

		self.draw_solid = True
		self.draw_buf = {0:[]}

		self.playback_status = (False, 0)

		if not adjustment:
			adjustment = gtk.Adjustment(0, 0, 8000*60, page_size=8000*60)
		self.set_adjustment(adjustment)

	def do_realize(self):
		self.set_flags(gtk.REALIZED)
		self.window = gtk.gdk.Window(
				self.get_parent_window(), 
				width=self.allocation.width, 
				height=self.allocation.height, 
				window_type=gtk.gdk.WINDOW_CHILD, 
				wclass=gtk.gdk.INPUT_OUTPUT,
				event_mask=gtk.gdk.EXPOSURE_MASK |
					gtk.gdk.BUTTON_PRESS_MASK |
					gtk.gdk.BUTTON_RELEASE_MASK |
					gtk.gdk.ENTER_NOTIFY_MASK |
					gtk.gdk.LEAVE_NOTIFY_MASK |
					gtk.gdk.POINTER_MOTION_MASK |
					gtk.gdk.POINTER_MOTION_HINT_MASK)
		self.window.set_user_data(self)
		self.style.attach(self.window)
		self.style.set_background(self.window, gtk.STATE_NORMAL)
		self.window.move_resize(*self.allocation)

		self.update_palette(self.DEFAULT_PALETTE)
		self.create_pixmap()
		self.paint_pixmap()

	def do_unrealize(self):
		self.window.set_user_data(None)
		self.player.dispose()

	def do_size_request(self, requisition):
		requisition.width = 200
		requisition.height = 100

	def do_size_allocate(self, allocation):
		self.allocation = allocation
		self.update_metrics()
		if self.flags() & gtk.REALIZED:
			self.window.move_resize(*allocation)
			self.update_draw_buffer()
			self.create_pixmap()
			self.paint_pixmap()

	def do_state_changed(self, state):
		self.paint_pixmap()
		self.queue_draw()

	def do_key_press_event(self, event):
		if event.keyval == ord(" "):
			self.player.toggle_play_state()

	def do_expose_event(self, event):
		self.window.draw_drawable(self.style.black_gc, 
				self.offscreen_pixmap, 
				event.area.x, event.area.y, 
				event.area.x, event.area.y, 
				event.area.width, event.area.height)

	def do_button_press_event(self, event):
		if event.type == gtk.gdk.BUTTON_PRESS:
			if not self.is_focus():
				self.grab_focus()

	def do_enter_notify_event(self, event):
		if self.get_property("sensitive"):
			self.window.set_cursor(self.cursor)
			self.set_state(gtk.STATE_PRELIGHT)

	def do_leave_notify_event(self, event):
		if self.get_property("sensitive"):
			self.window.set_cursor(None)
			self.set_state(gtk.STATE_NORMAL)

	def do_motion_notify_event(self, event):
		x_cut_in = self.frame_to_x(self.fr_cut_in)
		x_cut_out = self.frame_to_x(self.fr_cut_out)
		if x_cut_in < event.x and event.x < x_cut_out:
			if event.state & gtk.gdk.BUTTON1_MASK:
				self.x_cue_pos = int(event.x)
				self.paint_pixmap()
				self.queue_draw()

	def do_scroll_event(self, event):
		if not self.caps: return
		fr = self.x_to_frame(event.x)
		if event.direction == gtk.gdk.SCROLL_DOWN:
			if event.state & gtk.gdk.CONTROL_MASK:
				self.update_viewport(self.VIEWPORT_PAN_LEFT, fr)
			else:
				self.update_viewport(self.VIEWPORT_ZOOM_OUT, fr)
		elif event.direction == gtk.gdk.SCROLL_UP:
			if event.state & gtk.gdk.CONTROL_MASK:
				self.update_viewport(self.VIEWPORT_PAN_RIGHT, fr)
			else:
				self.update_viewport(self.VIEWPORT_ZOOM_IN, fr)
		elif event.direction == gtk.gdk.SCROLL_LEFT:
			self.update_viewport(self.VIEWPORT_PAN_LEFT, fr)
		elif event.direction == gtk.gdk.SCROLL_RIGHT:
			self.update_viewport(self.VIEWPORT_PAN_RIGHT, fr)

	def update_palette(self, palette):
		if not self.flags() & gtk.REALIZED:
			return
		self.palette.clear()
		self.gc.clear()
		colormap = self.window.get_colormap()
		for key, color in palette.iteritems():
			self.palette[key] = colormap.alloc_color(color)
			self.gc[key] = self.window.new_gc(foreground=self.palette[key])
		self.gc["center"].set_values(line_style=gtk.gdk.LINE_ON_OFF_DASH)

	def create_pixmap(self):
		w, h = self.window.get_size()
		self.offscreen_pixmap = gtk.gdk.Pixmap(self.window, w, h)

	def paint_pixmap(self):
		if not self.offscreen_pixmap:
			return
		canvas = self.offscreen_pixmap

		gc = self.style.bg_gc[self.state]
		w, h = self.window.get_size()
		canvas.draw_rectangle(gc, True, 0, 0, w, h)

		if not self.get_property("sensitive"):
			return

		channels = self.get_channels()

		ch_height = self.metrics.get_channel_height()
		grid_ys   = self.metrics.get_grid_lines()
		tick_ys   = self.metrics.get_ticks()
		label_ys  = self.metrics.get_labels()
		x_array   = self.metrics.get_x_array()
		timetick  = self.metrics.get_timetick()
		timetag   = self.metrics.get_timetag()
		center_y  = self.metrics.get_center()
		layout    = self.layout10

		cut_in = self.fr_cut_in
		cut_out = self.fr_cut_out
		x_cut_in = self.frame_to_x(cut_in)
		x_cut_out = self.frame_to_x(cut_out)
		draw_in = int(self.adjustment.value)
		draw_out = draw_in + int(self.adjustment.page_size)
		#print "draw_in", draw_in, "x_draw_in", self.frame_to_x(draw_in), 
		#print "draw_out", draw_out, "x_draw_out", self.frame_to_x(draw_out)
		#print "cut_in", cut_in, "cut_out", cut_out, 
		#print "x_cut_in", x_cut_in, "x_cut_out", x_cut_out

		# draw sound graph
		hh = (ch_height-1)*.5
		canvas.draw_rectangle(self.gc["grid"], True, 0, 0, w, h)
		for ch in range(channels):
			if ch % 2 == 0:
				gc_in = self.gc["odd_in"]
				gc_out = self.gc["odd_out"]
			else:
				gc_in = self.gc["even_in"]
				gc_out = self.gc["even_out"]
			by = self.metrics.get_channel_base_y(ch)
			# channel background
			canvas.draw_rectangle(self.gc["chnl_out"], True, 0, by, w, ch_height-1)
			canvas.draw_rectangle(self.gc["chnl_in"], True, x_cut_in, by, x_cut_out-x_cut_in, ch_height-1)
			# volume grid
			if True:
				for y in grid_ys:
					canvas.draw_line(self.gc["grid"], 0, y+by, w, y+by)
			# time grid
			for x in x_array:
				canvas.draw_line(self.gc["grid"], x, by, x, by+ch_height-1)
			# wave form
			yy = by + center_y
			if self.draw_solid:
				for x, (high, low) in enumerate(self.draw_buf[ch]):
					dh = int(yy - hh * high/128.)
					dl = int(yy - hh * low/128.)
					if x < x_cut_in or x > x_cut_out:
						canvas.draw_line(gc_out, x, dh, x, dl)
					else:
						canvas.draw_line(gc_in, x, dh, x, dl)
			else:
				draw_in = int(self.adjustment.value)
				x0 = -1
				y0 = yy
				for i, v in enumerate(self.draw_buf[ch]):
					fr = draw_in + i
					if fr < cut_in or fr >= cut_out:
						gc = gc_out
					else:
						gc = gc_in
					x = self.frame_to_x(fr+1) - 1
					y = int(yy - hh * v/128.)
					canvas.draw_line(gc, x0, y0, x0+1, y)
					canvas.draw_line(gc, x0+1, y, x, y)
					x0, y0 = x, y
			# volume tick
			if True:
				for y, x in tick_ys:
					canvas.draw_line(self.gc["tick"], 0, y+by, x, y+by)
			# volume label
			if True:
				for y, text in label_ys:
					layout.set_text(text)
					tw, th = layout.get_pixel_size()
					canvas.draw_layout(self.gc["tick"], 28-tw, y+by-2, layout)
			# center line
			canvas.draw_line(self.gc["center"], 0, by+center_y, w-1, by+center_y)

		if self.x_cue_pos >= 0:
			canvas.draw_line(self.style.white_gc, self.x_cue_pos, 0, self.x_cue_pos, h-1)
			layout = self.layout9
			layout.set_text("%.3f" % self.get_cue_time())
			canvas.draw_layout(self.style.white_gc, self.x_cue_pos+2, 80, layout)

		# draw boundary
		#print "boundary", "x_cut_in", x_cut_in, "x_cut_out", x_cut_out
		# this is a ugly solution for black out problem
		# each statement works fine without the other when causes problem
		# when put together
		if x_cut_in >= 0 and x_cut_in < w:
			canvas.draw_line(self.gc["boundary"], x_cut_in, 0, x_cut_in, h-1)
		canvas.draw_line(self.gc["boundary"], x_cut_out, 0, x_cut_out, h-1)

		if self.playback_status[0]:
			x_is = self.time_to_x(self.playback_status[1])
			canvas.draw_line(self.style.white_gc, x_is, 0, x_is, h-27)
			canvas.draw_line(self.style.black_gc, x_is-1, 0, x_is-1, h-27)

		# draw cue slot
		canvas.draw_line(self.style.white_gc, 0, h-26, w-1, h-26)
		canvas.draw_rectangle(self.style.black_gc, True, 0, h-25, w, 9)
		canvas.draw_line(self.gc["grid"], 0, h-25, w-1, h-25)
		for x in x_array:
			canvas.draw_line(self.gc["grid"], x, h-25, x, h-17)

		# draw time line
		layout = self.layout10
		canvas.draw_line(self.style.white_gc, 0, h-16, w-1, h-16)
		canvas.draw_rectangle(self.style.bg_gc[gtk.STATE_ACTIVE], True, 0, h-15, w, 15)
		for x, y in timetick:
			canvas.draw_line(self.style.fg_gc[gtk.STATE_NORMAL], x, h-15, x, h-15+y)
		for x, text in timetag:
			layout.set_text(text)
			canvas.draw_layout(self.style.fg_gc[gtk.STATE_NORMAL], x+2, h-15, layout)

	def update_draw_buffer(self):
		w = self.allocation.width
		self.draw_solid = True
		channels = self.get_channels()
		self.draw_buf = dict([(ch, []) for ch in range(channels)])
		if not True:
			for ch in range(channels):
				for x in range(w - 1):
					v = math.sin(math.pi * 4 * x / w + math.pi * ch * .5) * 128
					self.draw_buf[ch].append([max(v, 0), min(v, 0)])
			return

		draw_count = int(self.adjustment.page_size)
		draw_in = int(self.adjustment.value)
		draw_out = draw_in + draw_count
		slice = w - 1
		padding = 0
		pace = 1
		max_offset = len(self.data) - 1
		frames_per_pixel = float(draw_count) / slice
		if frames_per_pixel <= 2:
			self.draw_solid = False
			for fr in range(draw_in, draw_out, pace):
				offset = (fr - padding) * channels
				for ch in range(channels):
					ii = offset + ch
					if ii > max_offset:
						value = 0
					else:
						value = self.data[ii]
					self.draw_buf[ch].append(value)
			return
		else:
			for x in range(w):
				for ch in range(channels):
					self.draw_buf[ch].append([0, 0])
			pace = 1
			if frames_per_pixel > 20:
				pace = int(frames_per_pixel / 20)
			for x in range(w):
				base_fr = self.x_to_frame(x)
				for fr in range(0, int(frames_per_pixel), pace):
					offset = (fr+base_fr) * channels
					ch = 0
					while ch < channels and offset <= max_offset:
						self.draw_buf[ch][x][0] = max(self.draw_buf[ch][x][0], self.data[offset])
						self.draw_buf[ch][x][1] = min(self.draw_buf[ch][x][1], self.data[offset])
						offset += 1
						ch += 1

	def update_metrics(self):
		w = max(self.allocation.width, 200)
		h = max(self.allocation.height, 100) - 26
		self.metrics.update(w, h, self.get_rate(), self.get_channels(), 
				self.adjustment.value, 
				self.adjustment.value+self.adjustment.page_size)

	def update_viewport(self, action, fr_hint):
		draw_count = int(self.adjustment.page_size)
		draw_in = int(self.adjustment.value)
		draw_out = draw_in + draw_count
		total_frames = int(self.adjustment.upper)
		if action == self.VIEWPORT_PAN_LEFT:
			new_draw_in = max(0, draw_in - draw_count)
			if draw_in == new_draw_in:
				return
			self.adjustment.set_value(new_draw_in)
		elif action == self.VIEWPORT_PAN_RIGHT:
			new_draw_out = min(total_frames, draw_out + draw_count)
			if draw_out == new_draw_out:
				return
			self.adjustment.set_value(new_draw_out - draw_count)
		elif action == self.VIEWPORT_ZOOM_IN:
			new_draw_count = max(1, draw_count / 2)
			if draw_count == new_draw_count:
				return
			new_draw_in = fr_hint - new_draw_count / 2
			new_draw_out = new_draw_in + new_draw_count
			if new_draw_in < 0:
				new_draw_in = 0
				new_draw_out = new_draw_count
			elif new_draw_out > total_frames:
				new_draw_out = total_frames
				new_draw_in = new_draw_out - new_draw_count
			self.adjustment.set_all(new_draw_in, 0, total_frames, 
					new_draw_count, new_draw_count, new_draw_count)
		elif action == self.VIEWPORT_ZOOM_OUT:
			new_draw_count = min(total_frames, draw_count * 2)
			if draw_count == new_draw_count:
				return
			new_draw_in = fr_hint - new_draw_count / 2
			new_draw_out = new_draw_in + new_draw_count
			if new_draw_in < 0:
				new_draw_in = 0
				new_draw_out = new_draw_count
			elif new_draw_out > total_frames:
				new_draw_out = total_frames
				new_draw_in = new_draw_out - new_draw_count
			self.adjustment.set_all(new_draw_in, 0, total_frames,
					new_draw_count, new_draw_count, new_draw_count)

	#####################################

	def new_load_media_file(self, filepath):
		thread_id = self.loader_thread_id
		loader = SampleLoader(self, thread_id, filepath)

	def on_adjustment_changed(self, adjustment):
		self.update_metrics()
		self.update_draw_buffer()
		self.paint_pixmap()
		self.queue_draw()

	def on_adjustment_value_changed(self, adjustment):
		self.update_metrics()
		self.update_draw_buffer()
		self.paint_pixmap()
		self.queue_draw()

	def reset(self):
		self.audiofile = ""
		self.caps = None
		self.adjustment.set_all(0, 0, 0, 0, 0)
		self.data = array.array("b")
		self.load_thread_id = -1
		self.set_tooltip_text(None)

	##########################################
	# coordinates conversion utility methods #
	##########################################

	def frame_to_x(self, fr):
		draw_in = self.adjustment.value
		draw_count = self.adjustment.page_size
		slice = self.allocation.width - 1.0
		if fr < draw_in:
			return -1
		elif fr > draw_in + draw_count * (1+1./slice):
			return self.allocation.width
		x = int((fr - draw_in) * slice / draw_count)
		return x

	def x_to_frame(self, x):
		draw_in = self.adjustment.value
		draw_count = self.adjustment.page_size
		slice = self.allocation.width - 1.0
		fr = int(x * draw_count / slice + draw_in)
		return min(fr, int(self.adjustment.upper))

	def time_to_x(self, t):
		draw_in = self.adjustment.value
		draw_count = self.adjustment.page_size
		slice = self.allocation.width - 1.0
		rate = self.get_rate()
		x = int((t * rate - draw_in) * slice / draw_count)
		return x

	def x_to_time(self, x):
		return float(self.x_to_frame(x)) / self.get_rate()

	def time_to_frame(self, timestamp):
		return int(round(timestamp * self.get_rate()))

	##################################
	# AudioManager interface methods #
	##################################

	def get_rate(self):
		if not self.caps:
			return 8000
		return self.caps["rate"]

	def get_channels(self):
		if not self.caps:
			return 1
		return self.caps["channels"]

	###################################
	# DisplayController interface     #
	###################################

	def set_adjustment(self, adjustment):
		if self.adjustment:
			self.adjustment.disconnect(self.handler_id_changed)
			self.adjustment.disconnect(self.handler_id_value_changed)
			self.adjustment = None
			self.handler_id_changed = -1
			self.handler_id_value_changed = -1
		self.adjustment = adjustment
		self.handler_id_changed = self.adjustment.connect(
				"changed", self.on_adjustment_changed)
		self.handler_id_value_changed = self.adjustment.connect(
				"value-changed", self.on_adjustment_value_changed)
		self.paint_pixmap()
		self.queue_draw()

	############################
	# INTERFACE CALLBACKS      #
	############################

	#-----------------------------------+
	# interface visible to SampleLoader |
	#-----------------------------------+

	def format_detected(self, token, caps, total_frames):
		if token != self.loader_thread_id:
			return
		self.caps = caps
		self.fr_cut_in = 0
		self.fr_cut_out = total_frames
		self.adjustment.set_all(0, 0, total_frames,  
				step_increment=total_frames, 
				page_increment=total_frames, 
				page_size=total_frames)
		self.emit("audio-format-changed", caps, total_frames)

	def sample_data_loaded(self, token, new_data, has_more):
		if token != self.loader_thread_id:
			return False
		gtk.gdk.threads_enter()
		self.data.extend(new_data)
		if not has_more:
			self.update_draw_buffer()
			self.paint_pixmap()
			self.queue_draw()
		gtk.gdk.threads_leave()
		self.emit("sample-data-changed")
		return has_more

	#-----------------------------+
	# interface visible to Player |
	#-----------------------------+

	def update_playback_status(self, is_playing, pos_is):
		self.playback_status = (is_playing, pos_is)
		if self.flags() & gtk.REALIZED:
			if is_playing:
				if self.time_to_x(pos_is) >= self.allocation.width:
					self.update_viewport(self.VIEWPORT_PAN_RIGHT, None)
				else:
					gtk.gdk.threads_enter()
					self.paint_pixmap()
					gtk.gdk.threads_leave()
					self.queue_draw()

	#--------------------------------+
	# interface visible to tdfplayer |
	#--------------------------------+

	def set_media_file(self, filepath):
		self.reset()
		if not filepath:
			return
		if not os.path.exists(filepath):
			raise RuntimeError, os.strerror(errno.ENOENT)
		elif os.path.isdir(filepath):
			raise RuntimeError, os.strerror(errno.EISDIR)

		self.player.dispose()
		self.player = Player(self)
		self.player.set_file(filepath)
		self.loader_thread_id = thread.start_new_thread(
				self.new_load_media_file, (filepath,))

	def set_selection_by_time(self, cut_in_time, cut_out_time):
		fr_cut_in = self.time_to_frame(cut_in_time)
		fr_cut_out = self.time_to_frame(cut_out_time)
		if fr_cut_in != self.fr_cut_in or fr_cut_out != self.fr_cut_out:
			self.x_cue_pos = -1
			self.fr_cut_in = fr_cut_in
			self.fr_cut_out = fr_cut_out
			self.paint_pixmap()
			self.queue_draw()

	def set_viewport_by_time(self, disp_in_time, disp_out_time):
		fr_disp_in = max(0, self.time_to_frame(disp_in_time))
		fr_disp_out = self.time_to_frame(disp_out_time)
		viewport_size = fr_disp_out - fr_disp_in
		if fr_disp_in != self.adjustment.value or fr_disp_out != (
				self.adjustment.value + self.adjustment.page_size):
			self.adjustment.set_all(fr_disp_in, 0, max(self.adjustment.upper, fr_disp_out), 
					viewport_size, viewport_size, viewport_size)

	def get_cue_time(self):
		return self.x_to_time(self.x_cue_pos)

# end of class WavForm

# end of $URL$

