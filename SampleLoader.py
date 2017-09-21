#!/usr/bin/python

import os, array, time, math
import gobject
import gst

class SampleLoader:
	def __init__(self, client, token, filename):
		self.client = client
		self.token  = token

		self.done   = False
		self.error  = False
		self.eos    = False

		r_fd, w_fd   = os.pipe()
		event_source = gobject.io_add_watch(r_fd, 
				gobject.IO_IN, self.pipe_data_cb)

		pipeline     = gst.element_factory_make("pipeline", "loader")
		filesrc      = gst.element_factory_make("filesrc", "loader.filesrc")
		decodebin    = gst.element_factory_make("decodebin", "loader.decodebin")
		audioconvert = gst.element_factory_make("audioconvert", "loader.audioconvert")
		capsfilter   = gst.element_factory_make("capsfilter", "loader.capsfilter")
		fdsink       = gst.element_factory_make("fdsink", "loader.fdsink")

		filesrc.set_property("location", filename)
		decodebin.connect("new-decoded-pad",
				lambda bin, pad, islast, sink: pad.link(sink), 
				audioconvert.get_pad("sink"))
		capsfilter.set_property("caps", gst.caps_from_string(
					"audio/x-raw-int,width=8,depth=8,"
					"signed=(boolean)true,endianness=1234"))
		fdsink.set_property("fd", w_fd)

		pipeline.add(filesrc, decodebin, audioconvert, capsfilter, fdsink)
		gst.element_link_many(filesrc, decodebin)
		gst.element_link_many(audioconvert, capsfilter, fdsink)

		bus = pipeline.get_bus()
		bus.add_signal_watch()
		bus.connect("message::eos", self.loader_eos_cb, pipeline)
		bus.connect("message::error", self.loader_eos_cb, pipeline)
		bus.connect("message::state-changed", self.loader_state_changed_cb, 
				pipeline, audioconvert)

		self.pipeline = pipeline
		time.sleep(0.1)     # allow caller finish its event handler
		pipeline.set_state(gst.STATE_PAUSED)
		while not (self.done or self.error):
			time.sleep(0.5)
		gobject.source_remove(event_source)
		os.close(r_fd)
		os.close(w_fd)

	def do_preroll_setup(self, caps, source_bytes):
		total_samples = source_bytes / (caps["width"] / 8)
		frames = total_samples / caps["channels"]

		# notify client audio format information
		self.client.format_detected(self.token, caps, frames)

		self.expected_bytes = total_samples # one byte per sample after conversion
		self.received_bytes = 0
		self.stride = max(int(math.ceil(self.expected_bytes/100)), 16384)
		self.next_check_point = min(self.expected_bytes, self.stride)

		# buffer to cache sample data between each "PUSH" call
		self.sample_buffer = array.array("b")

		self.pipeline.set_state(gst.STATE_PLAYING)

	def pipe_data_cb(self, fd, condition):
		buf = os.read(fd, 16384)
		new_load = array.array("b", buf)
		self.received_bytes += len(new_load)
		self.sample_buffer.extend(new_load)
		has_more = (self.received_bytes < self.expected_bytes)
		repeat = True
		if self.received_bytes >= self.next_check_point or not has_more:
			self.next_check_point += self.stride
			repeat = self.client.sample_data_loaded(self.token, self.sample_buffer, has_more)
			#print "bytes loaded", self.received_bytes,
			#print "has more", has_more, 
			#print "remaining", self.expected_bytes - self.received_bytes, 
			#print "continue", repeat
			self.sample_buffer = array.array("b")
		self.done = not (has_more and repeat)
		return has_more and repeat

	def loader_eos_cb(self, bus, msg, pipeline):
		pipeline.set_state(gst.STATE_NULL)
		self.eos = True

	def loader_error_cb(self, bus, msg, pipeline):
		pipeline.set_state(gst.STATE_NULL)
		self.error = True

	def loader_state_changed_cb(self, bus, msg, pipeline, audioconvert):
		if msg.src != pipeline: return
		oldstate, newstate, pending = msg.parse_state_changed()
		if newstate != gst.STATE_PAUSED: return
		caps = audioconvert.get_pad("sink").get_negotiated_caps()[0]
		source_bytes = audioconvert.query_duration(gst.FORMAT_BYTES)[0]
		self.do_preroll_setup(caps, source_bytes)
# end of SampleLoader

# end of $URL$

