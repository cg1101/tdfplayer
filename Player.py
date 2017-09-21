#!/usr/bin/python

import thread, time
import gst

class Player:
	def __init__(self, client):
		self.client = client

		pipeline     = gst.element_factory_make("pipeline", "player")
		filesrc      = gst.element_factory_make("filesrc", "player.filesrc")
		decodebin    = gst.element_factory_make("decodebin", "player.decodebin")
		audioconvert = gst.element_factory_make("audioconvert", "player.audioconvert")
		try:
			sink         = gst.element_factory_make("pulsesink", "player.pulsesink")
		except:
			sink         = gst.element_factory_make("osxaudiosink", "player.osxaudiosink")

		decodebin.connect("new-decoded-pad",
				lambda bin, pad, islast, sink: pad.link(sink), 
				audioconvert.get_pad("sink"))

		pipeline.add(filesrc, decodebin, audioconvert, sink)
		gst.element_link_many(filesrc, decodebin)
		gst.element_link_many(audioconvert, sink)

		bus = pipeline.get_bus()
		bus.add_signal_watch()
		bus.connect("message::eos", self.player_eos_cb)
		bus.connect("message::error", self.player_eos_cb)
		bus.connect("message::state-changed", self.player_state_changed_cb)
		
		self.pipeline = pipeline
		self.is_playable = False
		self.is_playing = False
		self.playback_tracker_id = 0

	def dispose(self):
		self.pipeline.set_state(gst.STATE_NULL)
		self.is_playing = False
		time.sleep(0.1)

	def set_file(self, filepath, start_playback=False):
		if self.is_playing:
			self.pipeline.set_state(gst.STATE_NULL)
		self.is_playable = False
		self.is_playing = False
		if not filepath:
			return
		filesrc = self.pipeline.get_by_name("player.filesrc")
		filesrc.set_property("location", filepath)
		self.is_playable = True
		if start_playback:
			self.pipeline.set_state(gst.STATE_PLAYING)
		else:
			self.pipeline.set_state(gst.STATE_PAUSED)

	def play(self, t_cut_in=0, t_cut_out=0):
		if not self.is_playable or self.is_playing:
			return
		if t_cut_in > t_cut_out:
			t_cut_in, t_cut_out = t_cut_out, t_cut_in
		t_cut_in = int(t_cut_in * gst.SECOND)
		t_cut_out = int(t_cut_out * gst.SECOND)
		self.pipeline.set_state(gst.STATE_PAUSED)
		self.pipeline.seek(1.0, gst.FORMAT_TIME, 
				gst.SEEK_FLAG_FLUSH, 
				gst.SEEK_TYPE_SET, t_cut_in,  
				gst.SEEK_TYPE_SET if t_cut_out else gst.SEEK_TYPE_END, t_cut_out)
		self.pipeline.set_state(gst.STATE_PLAYING)

	def stop(self):
		if self.is_playable:
			self.pipeline.set_state(gst.STATE_PAUSED)

	def toggle_play_state(self, t_cut_in=0, t_cut_out=0):
		if self.is_playing:
			self.stop()
		else:
			self.play(t_cut_in, t_cut_out)

	def playback_tracker(self, client):
		my_id = self.playback_tracker_id
		while self.playback_tracker_id == my_id and self.is_playing:
			try:
				position, fmt = self.pipeline.query_position(
						gst.FORMAT_TIME)
				pos_is = float(position) / gst.SECOND
				client.update_playback_status(True, pos_is)
			except gst.QueryError, e:
				pass
			time.sleep(0.05)
		if self.playback_tracker_id == my_id:
			self.playback_tracker_id = 0
			client.update_playback_status(False, 0)

	def player_eos_cb(self, bus, msg):
		self.pipeline.set_state(gst.STATE_PAUSED)

	def player_error_cb(self, bus, msg):
		self.is_playable = False
		self.is_playing = False
		self.pipeline.set_state(gst.STATE_NULL)

	def player_state_changed_cb(self, bus, msg):
		if msg.src != self.pipeline: return
		oldstate, newstate, pending = msg.parse_state_changed()
		self.is_playing = (newstate == gst.STATE_PLAYING)
		if self.is_playing:
			self.playback_tracker_id = thread.start_new_thread(
					self.playback_tracker, (self.client,))
# end of class Player

