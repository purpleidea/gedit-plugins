# -*- coding: utf-8 -*-
#  Color picker plugin
#  This file is part of gedit-plugins
#
#  Copyright (C) 2006 Jesse van den Kieboom
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
#  Foundation, Inc., 59 Temple Place, Suite 330,
#  Boston, MA 02111-1307, USA.

from gi.repository import GObject, Gtk, Gdk, Gedit
import re
import gettext
from gpdefs import *

try:
    gettext.bindtextdomain(GETTEXT_PACKAGE, GP_LOCALEDIR)
    _ = lambda s: gettext.dgettext(GETTEXT_PACKAGE, s);
except:
    _ = lambda s: s

ui_str = """
<ui>
  <menubar name="MenuBar">
    <menu name="ToolsMenu" action="Tools">
      <placeholder name="ToolsOps_2">
        <menuitem name="ColorPicker" action="ColorPicker"/>
      </placeholder>
    </menu>
  </menubar>
</ui>
"""

class ColorPickerPlugin(GObject.Object, Gedit.WindowActivatable):
    __gtype_name__ = "ColorPickerPlugin"

    window = GObject.property(type=Gedit.Window)

    def __init__(self):
        GObject.Object.__init__(self)
        self._dialog = None

    def do_activate(self):
        self._insert_menu()
        self._update()

    def do_deactivate(self):
        self._remove_menu()

    def do_update_state(self):
        self._update()

    def _update(self):
        tab = self.window.get_active_tab()
        self._action_group.set_sensitive(tab != None)

        if not tab and self._dialog and \
                self._dialog.get_transient_for() == self.window:
            self._dialog.response(Gtk.ResponseType.CLOSE)

    def _insert_menu(self):
        manager = self.window.get_ui_manager()
        self._action_group = Gtk.ActionGroup(name="GeditColorPickerPluginActions")
        self._action_group.add_actions(
                [("ColorPicker", None, _("Pick _Color..."), None,
                 _("Pick a color from a dialog"),
                 lambda a: self.on_color_picker_activate())])

        manager.insert_action_group(self._action_group)
        self._ui_id = manager.add_ui_from_string(ui_str)

    def _remove_menu(self):
        manager = self.window.get_ui_manager()
        manager.remove_ui(self._ui_id)
        manager.remove_action_group(self._action_group)
        manager.ensure_update()

    def skip_hex(self, buf, iter, next_char):
        while True:
            char = iter.get_char()

            if not char:
                return

            if char.lower() not in \
                    ('0', '1', '2', '3', '4', '5', '6', '7', '8', '9',
                    'a', 'b', 'c', 'd', 'e', 'f'):
                return

            if not next_char(iter):
                return

    def get_rgba_position(self, buf):
        bounds = buf.get_selection_bounds()
        if bounds == ():
            # No selection, find color in the current cursor position
            start = buf.get_iter_at_mark(buf.get_insert())

            end = start.copy()
            start.backward_char()

            self.skip_hex(buf, start, lambda iter: iter.backward_char())
            self.skip_hex(buf, end, lambda iter: iter.forward_char())
        else:
            start, end = bounds

        text = buf.get_text(start, end, False)

        if not re.match('#?[0-9a-zA-Z]+', text):
            return None

        if text[0] != '#':
            start.backward_char()

            if start.get_char() != '#':
                return None

        return start, end

    def insert_color(self, text):
        view = self.window.get_active_view()

        if not view or not view.get_editable():
            return

        doc = view.get_buffer()

        if not doc:
            return

        doc.begin_user_action()

        # Get the color
        bounds = self.get_rgba_position(doc)

        if not bounds:
            doc.delete_selection(False, True)
        else:
            doc.delete(bounds[0], bounds[1])

        doc.insert_at_cursor('#' + text)

        doc.end_user_action()

    def scale_color_component(self, component):
        return min(max(int(round(component * 255.)), 0), 255)

    def get_current_color(self):
        doc = self.window.get_active_document()

        if not doc:
            return None

        bounds = self.get_rgba_position(doc)

        if bounds:
            return doc.get_text(bounds[0], bounds[1], False)
        else:
            return None

    # Signal handlers

    def on_color_picker_activate(self):
        if not self._dialog:
            self._dialog = Gtk.ColorChooserDialog(_('Pick Color'), self.window)

            self._dialog.connect('response', self.on_dialog_response)

        rgba_str = self.get_current_color()

        if rgba_str:
            rgba = Gdk.RGBA()
            parsed = rgba.parse(rgba_str)

            if parsed:
                self._dialog.set_rgba(rgba)

        self._dialog.present()

    def on_dialog_response(self, dialog, response):
        if response == Gtk.ResponseType.OK:
            rgba = Gdk.RGBA()
            dialog.get_rgba(rgba)

            self.insert_color("%02x%02x%02x" % (self.scale_color_component(rgba.red), \
                                                self.scale_color_component(rgba.green), \
                                                self.scale_color_component(rgba.blue)))
        else:
            self._dialog.destroy()
            self._dialog = None

# ex:ts=4:et:
