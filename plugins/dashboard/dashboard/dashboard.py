#!/usr/bin/env python
# -- coding: utf-8 --
#
# Copyright © 2011 Collabora Ltd.
#            By Seif Lotfy <seif@lotfy.com>
#
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor,
#  Boston, MA 02110-1301, USA.

from gi.repository import GObject, Gedit, Gtk, Gio, GLib, GdkPixbuf, GtkSource
from gi.repository import Zeitgeist
from .utils import *

import time
import os
import urllib
import dbus
import datetime

CLIENT = Zeitgeist.Log.get_default()

try:
    BUS = dbus.SessionBus()
    obj = BUS.get_object('org.gnome.zeitgeist.SimpleIndexer',
        '/org/gnome/zeitgeist/index/activity')
    iface = dbus.Interface(obj, 'org.gnome.zeitgeist.Index')
    ZG_FTS = Zeitgeist.Index.new()
except Exception as err:
    ZG_FTS = None
    print ("Could not detect FTS supports, disabling Dashboard search")

version = [int(x) for x in CLIENT.get_version()]

MIN_VERSION = [0, 9, 11, 0]
if version < MIN_VERSION:
    print("PLEASE USE ZEITGEIST 0.9.11 or above")

class Item(Gtk.Button):

    def __init__(self, subject):

        Gtk.Button.__init__(self)
        self._file_object = Gio.file_new_for_uri(subject.get_property("uri"))
        self._file_info =\
            self._file_object.query_info("standard::content-type",
            Gio.FileQueryInfoFlags.NONE, None)
        self.subject = subject
        SIZE_LARGE = (256, 256)
        self.thumb = create_text_thumb(self, SIZE_LARGE, 1)
        self.set_size_request(256, 256)
        vbox = Gtk.Box(orientation = Gtk.Orientation.VERTICAL)
        vbox.pack_start(self.thumb, True, True, 0)
        self.label = Gtk.Label()
        self.label.set_ellipsize(2)
        self.label.set_markup("<span size='large'><b>%s</b></span>"\
            %subject.get_property("text"))
        vbox.pack_start(self.label, False, False, 6)
        self.add(vbox)

    @property
    def mime_type(self):
        return self._file_info.get_attribute_string("standard::content-type")

    def get_content(self):
        f = open(self._file_object.get_path())
        try:
            content = f.read()
        finally:
            f.close()
        return content


class StockButton(Gtk.Button):

    def __init__(self, stock, label):
        Gtk.Button.__init__(self)
        self.set_size_request(256, 256)
        vbox = Gtk.Box(orientation = Gtk.Orientation.VERTICAL)
        self.label = Gtk.Label()
        self.label.set_markup("<span size='large'><b>%s</b></span>"%label)
        vbox.pack_end(self.label, False, False, 6)
        self.add(vbox)


class DashView(Gtk.Box):

    def __init__(self, show_doc, window):
        Gtk.Box.__init__(self, orientation = Gtk.Orientation.VERTICAL)
        hbox = Gtk.Box()
        self._window = window
        self.pack_start(Gtk.Label(""), True, True, 0)
        self.pack_start(hbox, False, False, 0)
        self.pack_start(Gtk.Label(""), True, True, 0)

        self.grid = Gtk.Grid()
        self.grid.set_row_homogeneous(True)
        self.grid.set_column_homogeneous(True)

        self.grid.set_column_spacing(15)
        self.grid.set_row_spacing(15)
        hbox.pack_start(Gtk.Label(""), True, True, 0)
        hbox.pack_start(self.grid, False, False, 0)
        hbox.pack_start(Gtk.Label(""), True, True, 0)

        self.new_button = StockButton(Gtk.STOCK_NEW, _("Empty Document"))
        self.new_button.connect("clicked", lambda x: show_doc())

    def populate_grid(self, subjects):
        for child in self.grid.get_children():
            self.grid.remove(child)
        self.hide()

        self.grid.add(self.new_button)
        self.show_all()

        for i, subject in enumerate(subjects):
            item = Item(subjects[i])
            item.connect("clicked", self.open)
            self.grid.attach(item, (i + 1) % 4, (i + 1) / 4, 1, 1)
        self.show_all()

    def open(self, item):
        Gedit.commands_load_location(self._window,
            item._file_object, None, -1, -1)


class SearchEntry(Gtk.Entry):

    __gsignals__ = {
        "clear": (GObject.SIGNAL_RUN_FIRST,
                   GObject.TYPE_NONE,
                   ()),
        "search": (GObject.SIGNAL_RUN_FIRST,
                    GObject.TYPE_NONE,
                    (GObject.TYPE_STRING,)),
        "close": (GObject.SIGNAL_RUN_FIRST,
                   GObject.TYPE_NONE,
                   ()),
    }

    search_timeout = 0

    def __init__(self, accel_group = None):
        Gtk.Entry.__init__(self)
        self.set_width_chars(40)
        self.set_placeholder_text(_("Type here to search..."))
        self.connect("changed", lambda w: self._queue_search())

        search_icon =\
            Gio.ThemedIcon.new_with_default_fallbacks("edit-find-symbolic")
        self.set_icon_from_gicon(Gtk.EntryIconPosition.PRIMARY, search_icon)
        clear_icon =\
            Gio.ThemedIcon.new_with_default_fallbacks("edit-clear-symbolic")
        self.set_icon_from_gicon(Gtk.EntryIconPosition.SECONDARY, clear_icon)
        self.connect("icon-press", self._icon_press)
        self.show_all()

    def _icon_press(self, widget, pos, event):
        if event.button == 1 and pos == 1:
            self.set_text("")
            self.emit("clear")

    def _queue_search(self):
        if self.search_timeout != 0:
            GObject.source_remove(self.search_timeout)
            self.search_timeout = 0

        if len(self.get_text()) == 0:
            self.emit("clear")
        else:
            self.search_timeout = GObject.timeout_add(200,
                self._typing_timeout)

    def _typing_timeout(self):
        if len(self.get_text()) > 0:
            self.emit("search", self.get_text())

        self.search_timeout = 0
        return False


class ListView(Gtk.TreeView):

    def __init__(self):
        Gtk.TreeView.__init__(self)
        self.icontheme = Gtk.IconTheme.get_default()
        self.model = Gtk.ListStore(str, GdkPixbuf.Pixbuf, str, str,
            GObject.TYPE_PYOBJECT)

        renderer_text = Gtk.CellRendererText()
        column_text = Gtk.TreeViewColumn("Text", renderer_text, markup=0)
        self.append_column(column_text)

        renderer_pixbuf = Gtk.CellRendererPixbuf()
        column_pixbuf = Gtk.TreeViewColumn("Image", renderer_pixbuf, pixbuf=1)
        self.append_column(column_pixbuf)

        renderer_text = Gtk.CellRendererText()
        renderer_text.set_alignment(0.0, 0.5)
        renderer_text.set_property('ellipsize', 1)
        column_text = Gtk.TreeViewColumn("Text", renderer_text, markup=2)
        column_text.set_expand(True)
        self.append_column(column_text)

        renderer_text = Gtk.CellRendererText()
        renderer_text.set_alignment(1.0, 0.5)
        column_text = Gtk.TreeViewColumn("Text", renderer_text, markup=3)
        self.append_column(column_text)

        self.style_get_property("horizontal-separator", 9)
        self.set_headers_visible(False)
        self.set_model(self.model)
        self.home_path = "file://%s" %os.getenv("HOME")
        self.now = time.time()

    def get_time_string(self, timestamp):
        timestamp = int(timestamp)/1000
        diff = int(self.now - timestamp)
        if diff < 60:
            return "   few moment ago   "
        diff = int(diff / 60)
        if diff < 60:
            if diff == 1:
                return "   %i minute ago   " %int(diff)
            return "   %i minutes ago   " %int(diff)
        diff = int(diff / 60)
        if diff < 24:
            if diff == 1:
                return "   %i hour ago   " %int(diff)
            return "   %i hours ago   " %int(diff)
        diff = int(diff / 24)
        if diff < 4:
            if diff == 1:
                return "   Yesterday   "
            return "   %i days ago   " %int(diff)

        return datetime.datetime.fromtimestamp(timestamp)\
            .strftime('   %d %B %Y   ')

    def clear(self):
        self.model.clear()
        self.now = time.time()

    def insert_results(self, log, res, data):
        events = log.search_finish(res)
        self.clear()
        for i in range(events.size()):
            event = events.next_value()
            self.add_item(event, 48)

    def add_item(self, event, icon_size):
        item = event.get_subject(0)
        if uri_exists(item.get_property("uri")):
            uri = item.get_property("uri").replace(self.home_path, "Home").split("/")
            uri = " → ".join(uri[:-1])
            text = """<span size='large'><b>
               %s\n</b></span><span color='darkgrey'>   %s
               </span>"""%(item.get_property("text"), uri)
            iter = self.model.append(["   ", no_pixbuf, text,
                "<span color='darkgrey'>   %s</span>"\
                %self.get_time_string(event.get_property("timestamp")), item])

            def callback(icon):
                self.model[iter][1] = icon if icon is not None else no_pixbuf
            get_icon(item, callback, icon_size)


class Dashboard (Gtk.Box):

    def __init__(self, window, show_doc):
        Gtk.Box.__init__(self, orientation = Gtk.Orientation.VERTICAL)
        self._window = window
        self._show_doc = show_doc
        self._init_done = False
        self.search = SearchEntry()

        if ZG_FTS:
            box = Gtk.Box()
            box.set_homogeneous(True)
            box.pack_start(Gtk.Label(), True, True, 0)
            box.pack_start(self.search, True, True, 0)
            box.pack_start(Gtk.Label(), True, True, 0)
            self.search.connect("search", self._on_search)
            self.search.connect("clear", self._on_clear)
            self.connect("draw", self.change_style)
            self.pack_start(box, False, False, 16)

        self.view = DashView(self._show_doc, window)
        scrolledwindow = Gtk.ScrolledWindow()
        vbox = Gtk.Box(orientation = Gtk.Orientation.VERTICAL)
        scrolledwindow.add(vbox)
        vbox.pack_start(self.view, True, True, 0)
        self.tree_view = ListView()
        vbox.pack_start(self.tree_view, True, True, 0)

        self.pack_start(scrolledwindow, True, True, 0)
        self.get_recent()
        self.show_all()

        def open_uri(widget, row, cell):
            Gedit.commands_load_location(self._window,
                Gio.file_new_for_uri(widget.model[row][4].get_property("uri")),
                    None, 0, 0)
        self.tree_view.connect("row-activated", open_uri)
        self.grab_focus()


    def grab_focus(self):
        if ZG_FTS:
            self.search.grab_focus()

    def _on_search(self, widget, query):
        self.tree_view.show()
        self.view.hide()
        print("Dashboard search for:", query)
        result_type_relevancy = 100
        self.template = Zeitgeist.Event()
        self.template.set_property("actor", "application://gedit.desktop")
        timerange = Zeitgeist.TimeRange.anytime()
        ZG_FTS.search(query + "*",
            timerange,
            [self.template],
            0, 100, 2, None, self.tree_view.insert_results, None)

    def _on_clear(self, widget):
        self.tree_view.hide()
        self.view.show()
        self.tree_view.clear()

    def change_style(self, widget, data):
        self.style = self.get_style_context()
        if self._init_done == False and ZG_FTS:
            self.search.grab_focus()
            self._init_done = True

    def get_recent(self):
        template = Zeitgeist.Event()
        template.set_property("actor", "application://gedit.desktop")
        CLIENT.find_events(
            Zeitgeist.TimeRange.anytime(),
            [template],
            Zeitgeist.StorageState.ANY,
            100,
            Zeitgeist.ResultType.MOST_RECENT_SUBJECTS,
            None,
            self.get_frequent,
            None)

    def get_frequent(self, log, res, data):
        events = CLIENT.find_events_finish(res)
        template = Zeitgeist.Event()
        template.set_property("actor", "application://gedit.desktop")
        now = time.time() * 1000
        # 14 being the amount of days
        # and 86400000 the amount of milliseconds per day
        two_weeks_in_ms = 14 * 86400000
        timerange = Zeitgeist.TimeRange.new(now - two_weeks_in_ms, now)
        CLIENT.find_events(
            timerange,
            [template],
            Zeitgeist.StorageState.ANY,
            100,
            Zeitgeist.ResultType.MOST_POPULAR_SUBJECTS,
            None,
            self.validate_results,
            events)

    def validate_results(self, log, res, data):
        recent_events = data
        popular_events = CLIENT.find_events_finish(res)
        subjects = []
        for events in (recent_events, popular_events,):
            allowed_len = 4 if events == recent_events else 7
            for i in range(events.size()):
                if len(subjects) == allowed_len:
                    break
                event = events.next_value()
                for i in range(event.num_subjects()):
                    subj = event.get_subject(i)
                    if uri_exists(subj.get_property("uri")):
                        subjects.append(subj)
                    if len(subjects) == allowed_len:
                        break
                if len(subjects) == allowed_len:
                    break
        self.view.populate_grid(subjects)

# ex:ts=4:et:
