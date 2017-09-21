#!/usr/bin/python

import math

def format_label(value, tick):
	if tick < 0.00001:
		fmtstr = "%02d:%02d:%09.6f"
	elif tick < 0.0001:
		fmtstr = "%02d:%02d:%08.5f"
	elif tick < 0.001:
		fmtstr = "%02d:%02d:%07.4f"
	elif tick < 0.01:
		fmtstr = "%02d:%02d:%06.3f"
	elif tick < 0.1:
		fmtstr = "%02d:%02d:%05.2f"
	elif tick < 1:
		fmtstr = "%02d:%02d:%04.1f"
	else:
		fmtstr = "%02d:%02d:%02.0f"
	hour = int(value) / 3600
	min  = int(value - hour * 3600) / 60
	sec  = value - hour * 3600 - min * 60
	return fmtstr % (hour, min, sec)
# end of format_label

TIME_SCALE_OPTIONS = [
	(5,  5, 0.000001), 
	(10, 5, 0.000002), 
	(5,  5, 0.00001), 
	(10, 5, 0.0001), 
	(10, 5, 0.0002), 
	(5,  5, 0.0001), 
	(10, 5, 0.0001), 
	(10, 5, 0.002), 
	(5,  5, 0.001), 
	(10, 5, 0.001), 
	(10, 5, 0.002), 
	(5,  5, 0.01), 
	(10, 5, 0.01), 
	(10, 5, 0.02), 
	(5,  5, 0.1), 
	(10, 5, 0.1), 
	(10, 5, 0.2), 
	(5,  5, 1), 
	(10, 5, 1), 
	(10, 5, 2), 
	(3,  3, 10), 
	(10, 5, 6), 
	(10, 5, 12), 
	(5,  5, 60), 
	(10, 5, 60), 
	(10, 5, 120), 
	(3,  3, 600), 
	(6,  3, 600), 
	(12, 6, 600), 
	(4,  4, 1800), 
	(8,  4, 1800), 
	(8,  4, 3600), 
	(12, 6, 3600), 
]

class Metrics:
	def __init__(self, layout, width=200, height=74, rate=8000, 
				channels=1, draw_in=0, draw_out=8000*60):
		self.layout = layout

		self.width    = width
		self.height   = height
		self.draw_in  = draw_in
		self.draw_out = draw_out

		self.rate     = rate
		self.channels = channels

		self.ch_stride = -1
		self.ticks = {}
		self.grids = []
		self.labels = []
		self.x_array = []
		self.timetick = []
		self.timetag = []

		self.update_volume_grid()
		self.update_time_grid()

	def update(self, width, height, rate, channels, draw_in, draw_out):
		if height != self.height or channels != self.channels:
			self.height = height
			self.channels = channels
			self.update_volume_grid()

		if (width != self.width or rate != self.rate or
				draw_in != self.draw_in or draw_out != self.draw_out):
			self.width = width
			self.rate = rate
			self.draw_in = draw_in
			self.draw_out = draw_out
			self.update_time_grid()

	def update_volume_grid(self):
		self.ch_stride = (self.height + 2.0) / self.channels
		h = round(self.ch_stride - 2) - 1
		start = 0
		if h >= 400:
			tick_stride, grid_stride, label_stride = 1, 5, 10
		elif h >= 200:
			tick_stride, grid_stride, label_stride = 2, 10, 20
		elif h >= 80:
			tick_stride, grid_stride, label_stride = 10, 50, 50
		elif h >= 40:
			tick_stride, grid_stride, label_stride = 10, 50, 100
		else:
			tick_stride, grid_stride, label_stride = 20, 100, 100
			start = 100
		self.ticks  = dict([(x, int(round(h * x / 200))) 
				for x in range(0, 201, tick_stride)])
		self.grids  = [x for x in range(0, 201, grid_stride)]
		self.labels = [x for x in range(start, 201, label_stride)]

	def update_time_grid(self):
		layout = self.layout
		pixel_per_sec = (self.width - 1.) * self.rate / \
				(self.draw_out - self.draw_in)
		time_scale = {}
		i = 0
		while not time_scale:
			if i < len(TIME_SCALE_OPTIONS) - 1:
				major, minor, tick = TIME_SCALE_OPTIONS[i]
				i += 1
			else:
				major = 12
				minor = 6
				tick *= 2
			pixel_per_grid  = pixel_per_sec * minor * tick
			if pixel_per_grid < 25:
				continue
			pixel_per_label = pixel_per_sec * major * tick
			max_label = format_label(self.draw_out * self.rate, tick)
			layout.set_text(max_label)
			label_width, label_height = layout.get_pixel_size()
			if label_width + 10 > pixel_per_label:
				continue
			time_scale = {"major": major, "minor": minor, "tick": tick}
			break
		sec_per_grid = time_scale["tick"] * time_scale["minor"]
		sec_draw_in = self.draw_in * 1.0 / self.rate
		sec_draw_out = self.draw_out * 1.0 / self.rate
		sec_start = math.floor(sec_draw_in / sec_per_grid) * sec_per_grid
		sec_curr = sec_start
		counter = 0
		self.x_array = []
		self.timetick = []
		self.timetag = []
		while sec_curr <= sec_draw_out:
			x = int(round((sec_curr - sec_draw_in) * pixel_per_sec))
			if counter % time_scale["major"] == 0:
				self.x_array.append(x)
				self.timetick.append((x, 5))
				self.timetag.append((x, format_label(sec_curr, time_scale["tick"])))
			elif counter % time_scale["minor"] == 0:
				self.x_array.append(x)
				self.timetick.append((x, 3))
			else:
				self.timetick.append((x, 1))
			counter += 1
			#sec_curr = sec_start + sec_per_grid * counter
			sec_curr = sec_start + time_scale["tick"] * counter

	def get_x_array(self):
		return self.x_array

	def get_timetick(self):
		return self.timetick

	def get_timetag(self):
		return self.timetag

	def get_channel_base_y(self, ch):
		return int(self.ch_stride * ch)

	def get_channel_height(self):
		return int(round(self.ch_stride - 2))

	def get_ticks(self):
		result = []
		for i in sorted(self.ticks):
			y = self.ticks[i]
			if i in self.labels:
				result.append((y, 7))
			elif i in self.grids:
				result.append((y, 3))
			else:
				result.append((y, 1))
		return result

	def get_grid_lines(self):
		return [self.ticks[i] for i in self.grids]

	def get_labels(self):
		result = []
		for i in self.labels[:-1]:
			result.append((self.ticks[i], "%.1f" % (1-i/100.)))
		return result

	def get_center(self):
		return self.ticks[100]

# end of class Metrics

# end of $URL$

