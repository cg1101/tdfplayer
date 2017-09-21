#!/usr/bin/env python
# -*- coding: utf8 -*-

import os
import atexit

import psycopg2
import cjson

__all__ = ["getTask"]

class Task(object):
	conn = psycopg2.connect(host="services", database="tdfplayer", user="tdfplayer")
	cursor = conn.cursor()
	@classmethod
	def getTask(klass, taskID):
		klass.cursor.execute("""
			SELECT taskid, name, inputdir, outputdir, audiopath
			FROM tasks
			WHERE taskid=%s
		""", (taskID,))
		klass.conn.commit()
		if klass.cursor.rowcount == 0:
			return None
		r = klass.cursor.fetchone()
		return Task(*r)
	@classmethod
	def shutdown(klass):
		klass.conn.close()
	def __init__(self, taskid, name, inputdir, outputdir, audiopath):
		self.taskid = taskid
		self.name = name
		self.inputdir = inputdir
		self.outputdir = outputdir
		self.audiopath = audiopath
	def checkOutAFile(self, who, where):
		cursor = self.cursor
		cursor.execute("""
			SELECT basename, filepath, login, ipaddress, checkout
			FROM tdffiles
			WHERE taskid=%s AND login=%s AND status='busy'
		""", (self.taskid, who))
		if cursor.rowcount > 0:
			basename, filepath, login, ipaddress, checkout = cursor.fetchone()
			output = os.path.join(self.outputdir, basename + "_by_%s" % who)
			cursor.connection.commit()
			return cjson.encode(dict(
					message="file %s has been checked out by %s from %s at %s" % (basename, login, ipaddress, checkout), 
					input=filepath, 
					output=output, 
				))

		cursor.execute("""
			UPDATE tdffiles
			SET status='busy', login=%s, ipaddress=%s, checkout=now()
			WHERE fileid=(
				SELECT fileid
				FROM tdffiles
				WHERE taskid=%s AND status='new'
				LIMIT 1)
			RETURNING basename, filepath
		""", (who, where, self.taskid))
		if cursor.rowcount == 0:
			cursor.connection.commit()
			return cjson.encode(dict(error="no more files available in task %s" % self.taskid))

		cursor.connection.commit()
		(basename, filepath,) = cursor.fetchone()
		output = os.path.join(self.outputdir, basename + "_by_%s" % who)
		return cjson.encode(dict(input=filepath, output=output))

	def checkInAFile(self, who):
		cursor = self.cursor
		cursor.execute("""
			SELECT fileid, basename
			FROM tdffiles
			WHERE taskid=%s AND status='busy' AND login=%s
		""", (self.taskid, who))
		if cursor.rowcount == 0:
			cursor.connection.commit()
			return cjson.encode(dict(error="no file has been checked out by %s" % who))

		(fileid, basename) = cursor.fetchone()
		ofn = basename + "_by_%s" % who
		if not os.path.exists(os.path.join(self.outputdir, ofn)):
			cursor.connection.commit()
			return cjson.encode(dict(error="output file %s not found in %s" % (ofn, self.outputdir)))

		cursor.execute("""
			UPDATE tdffiles
			SET checkin=now(), status='finished'
			WHERE fileid=%s
		""", (fileid,))
		cursor.connection.commit()
		return cjson.encode(dict())


atexit.register(lambda: Task.shutdown())

def getTask(taskID):
	return Task.getTask(taskID)

