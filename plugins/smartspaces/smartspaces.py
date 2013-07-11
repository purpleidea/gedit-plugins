# -*- coding: utf-8 -*-

#  smartspaces.py
#
#  Copyright (C) 2006 - Steve Frécinaux
#  Copyright (C) 2013 - Garrett Regier
#  Copyright (C) 2013 - James Shubin
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

import os
from gi.repository import GObject, Gtk, Gdk, GtkSource, Gedit, PeasGtk, Gio

DEBUG = False
# TODO: check that the boilerplate and the loading/unloading details work right

class SmartSpacesPluginSettings(GObject.Object, PeasGtk.Configurable):

    def do_create_configure_widget(self):
        settings = self.plugin_info.get_settings('org.gnome.gedit.plugins.smartspaces')
        path = os.path.join(self.plugin_info.get_data_dir(), 'gedit-smartspaces-plugin.ui')
        builder = Gtk.Builder()
        builder.add_from_file(path)
        backspace_checkbox = builder.get_object('backspace_checkbox')
        delete_checkbox = builder.get_object('delete_checkbox')
        arrows_checkbox = builder.get_object('arrows_checkbox')
        keypad_checkbox = builder.get_object('keypad_checkbox')

        settings.bind('smart-backspace', backspace_checkbox, 'active', Gio.SettingsBindFlags.DEFAULT)
        settings.bind('smart-delete', delete_checkbox, 'active', Gio.SettingsBindFlags.DEFAULT)
        settings.bind('smart-arrows', arrows_checkbox, 'active', Gio.SettingsBindFlags.DEFAULT)
        settings.bind('smart-kparrows', keypad_checkbox, 'active', Gio.SettingsBindFlags.DEFAULT)

        smartspaces_vbox = builder.get_object('smartspaces_vbox')
        return smartspaces_vbox

class SmartSpacesPlugin(GObject.Object, Gedit.ViewActivatable):
    __gtype_name__ = 'SmartSpacesPlugin'

    view = GObject.property(type=Gedit.View)

    def __init__(self):
        GObject.Object.__init__(self)

    def do_activate(self):
        self.settings = self.plugin_info.get_settings('org.gnome.gedit.plugins.smartspaces')

        self._handlers = [
            None,
            self.view.connect('notify::editable', self.on_notify),
            self.view.connect('notify::insert-spaces-instead-of-tabs', self.on_notify),
            self.settings.connect('changed', self.on_settings_changed)
        ]

        self.reconfigure()

    def do_deactivate(self):
        for handler in self._handlers:
            if handler is not None:
                self.view.disconnect(handler)

    def update_active(self):
        # Don't activate the feature if the buffer isn't editable or if
        # we're using tabs
        active = self.view.get_editable() and \
        self.view.get_insert_spaces_instead_of_tabs()

        if active and self._handlers[0] is None:
            self._handlers[0] = self.view.connect('key-press-event', self.on_key_press_event)
        elif not active and self._handlers[0] is not None:
            self.view.disconnect(self._handlers[0])
            self._handlers[0] = None

    def reconfigure(self):
        # load any settings you want here...
        pass

    def on_settings_changed(self, settings, key):
        self.reconfigure()

    def on_notify(self, view, pspec):
        self.update_active()

    def get_real_indent_width(self):
        indent_width = self.view.get_indent_width()

        if indent_width < 0:
             indent_width = self.view.get_tab_width()

        return indent_width

    def on_key_press_event(self, view, event):
        # only take care of backspace, shift+backspace, left, right, delete...
        mods = Gtk.accelerator_get_default_mod_mask()

        if DEBUG:
            print 'keyval: %s' % str(event.keyval)

        # FIXME: this condition is confusing as !
        bs_bool = event.keyval != Gdk.KEY_BackSpace or event.state & mods != 0 and event.state & mods != Gdk.ModifierType.SHIFT_MASK

        dl_bool = event.keyval != Gdk.KEY_Delete or event.state & mods != 0 and event.state & mods != Gdk.ModifierType.SHIFT_MASK

        if event.keyval in [Gdk.KEY_Left, Gdk.KEY_Right] and self.settings.get_boolean('smart-arrows'):
            return self.do_key_press_leftright(view, event, debug=DEBUG)

        elif event.keyval in [Gdk.KEY_KP_Left, Gdk.KEY_KP_Right] and self.settings.get_boolean('smart-kparrows'):
            return self.do_key_press_leftright(view, event, debug=DEBUG)

        elif not(bs_bool) and self.settings.get_boolean('smart-backspace'):
            return self.do_key_press_backspace(view, event)

        elif not(dl_bool) and self.settings.get_boolean('smart-delete'):
            return self.do_key_press_delete(view, event)

        else:
            return False

    def do_key_press_backspace(self, view, event):
        mods = Gtk.accelerator_get_default_mod_mask()
        if event.keyval != Gdk.KEY_BackSpace or event.state & mods != 0 and event.state & mods != Gdk.ModifierType.SHIFT_MASK:
            return False

        doc = view.get_buffer()
        if doc.get_has_selection():
            return False

        cur = doc.get_iter_at_mark(doc.get_insert())
        offset = cur.get_line_offset()

        if offset == 0:
            # We're at the begining of the line, so we can't obviously
            # unindent in this case
            return False

        start = cur.copy()
        prev = cur.copy()
        prev.backward_char()

        # If the previous chars are spaces, try to remove
        # them until the previous tab stop
        max_move = offset % self.get_real_indent_width()

        if max_move == 0:
            max_move = self.get_real_indent_width()

        moved = 0
        while moved < max_move and prev.get_char() == ' ':
            start.backward_char()
            moved += 1
            if not prev.backward_char():
                # we reached the start of the buffer
                break

        if moved == 0:
            # The iterator hasn't moved, it was not a space
            return False

        # Actually delete the spaces
        doc.begin_user_action()
        doc.delete(start, cur)
        doc.end_user_action()

        return True

    # NOTE: this algorithm isn't perfect, but will probably do the job. Ping me
    # if you find any corner cases that you'd like to be handled differently.
    def do_key_press_delete(self, view, event):
        mods = Gtk.accelerator_get_default_mod_mask()
        if event.keyval != Gdk.KEY_Delete or event.state & mods != 0 and event.state & mods != Gdk.ModifierType.SHIFT_MASK:
            return False

        doc = view.get_buffer()
        if doc.get_has_selection():
            return False

        cur = doc.get_iter_at_mark(doc.get_insert())
        offset = cur.get_line_offset()
        length = cur.get_chars_in_line()                # length of line

        if offset == length - 1:
            # We're at the end of the line, so we can't obviously
            # unindent in this case
            return False

        start = cur.copy()
        prev = cur.copy()
        #prev.forward_char()

        # If the previous chars are spaces, try to remove
        # them until the previous tab stop
        max_move = offset % self.get_real_indent_width()

        if max_move == 0:
            max_move = self.get_real_indent_width()

        moved = 0
        while moved < max_move and prev.get_char() == ' ':
            start.forward_char()
            moved += 1
            if not prev.forward_char():
                # we reached the start of the buffer
                break

        if moved == 0:
            # The iterator hasn't moved, it was not a space
            return False

        # Actually delete the spaces
        doc.begin_user_action()
        doc.delete(start, cur)
        doc.end_user_action()

        return True

    def do_key_press_leftright(self, view, event, debug=False):
        """
        Handle moving left and right over spaces as if they were tabs!
        Handle selection (shift) and control-selection (shift+control) too.
        Writing this function was off-by-one hell. Patch carefully and test
        extensively.
        """
        mods = Gtk.accelerator_get_default_mod_mask()

        if debug:
            print 'FUNCTION: do_key_press_leftright(keyval:%d)' % event.keyval

        both = bool(event.state & mods == Gdk.ModifierType.SHIFT_MASK | Gdk.ModifierType.CONTROL_MASK)
        if debug:
            print 'BOTH: %s' % both

        if both: shift = True
        else: shift = bool(event.state & mods == Gdk.ModifierType.SHIFT_MASK)
        if debug:
            print 'SHIFT: %s' % shift

        if both: control = True
        else: control = bool(event.state & mods == Gdk.ModifierType.CONTROL_MASK)
        if debug:
            print 'CONTROL: %s' % control

        if event.keyval != Gdk.KEY_Left and \
        event.keyval != Gdk.KEY_Right and \
        event.keyval != Gdk.KEY_KP_Left and \
        event.keyval != Gdk.KEY_KP_Right:
            return False

        doc = view.get_buffer()
        # NOTE: we don't do this because we want to work while under selection!
        #if doc.get_has_selection():
        #    return False

        tabwidth = self.get_real_indent_width()
        if debug:
            print 'TABWIDTH: %d' % tabwidth

        iterobj = doc.get_iter_at_mark(doc.get_insert())    # get cursor mark
        selecto = doc.get_iter_at_mark(doc.get_selection_bound())

        length = iterobj.get_chars_in_line()                # length of line
        if debug:
            print 'LENGTH: %d' % length

        offset = iterobj.get_line_offset()                  # an int
        if debug:
            print 'OFFSET: %d' % offset

        iter_a = doc.get_iter_at_mark(doc.get_insert())
        iter_a.set_line_offset(0)                           # move to start
        iter_b = doc.get_iter_at_mark(doc.get_insert())
        iter_b.forward_line()                               # move to end

        line_list = doc.get_slice(iter_a, iter_b, True)     # line as an array
        if length != len(line_list):                        # sanity check
            import inspect
            print '** (gedit:%s:%d): CRITICAL **: do_key_press_leftright: assertion `length == len(line_list)\' failed' % (__file__, inspect.currentframe().f_back.f_lineno)

        # if in the 'middle' of a tab, jump to edge
        lalign = ((tabwidth-offset) % tabwidth)
        ralign = (offset % tabwidth)

        if debug:
            print 'LALIGN: %d' % lalign
        if debug:
            print 'RALIGN: %d' % ralign

        space = True
        until = 0
        while until < len(line_list) and space:             # find continuous
            if line_list[until] != ' ':
                space = False
                break
            until = until + 1

        if debug:
            print 'UNTIL: %d' % until

        motion = 1  # cursor moves itself by this (1)
        if event.keyval == Gdk.KEY_Left:

            if offset == 0:     # start of line
                return False

            # not within continuous initial indentation
            if offset > until and line_list[offset-1] != ' ':
                return False

            if line_list[offset-1] == ' ':
                space = True
                luntil = offset
                while luntil > 0 and space:             # find continuous
                    if line_list[luntil-1] != ' ':
                        space = False
                        break
                    luntil = luntil - 1

                if debug:
                    print 'LUNTIL: %d' % luntil
                iterobj.set_line_offset( max(offset - (tabwidth-lalign) + motion, luntil+1) )
            else:
                iterobj.set_line_offset( offset - (tabwidth-lalign) + motion )

        if event.keyval == Gdk.KEY_Right:

            if offset == length-1:  # end of line
                return False

            if offset > until-1 and line_list[offset+0] != ' ':     # not within continuous initial indentation
                return False

            if line_list[offset+0] == ' ':
                space = True
                runtil = offset
                while runtil < length and space:                # find continuous
                    if line_list[runtil+0] != ' ':
                        space = False
                        break
                    runtil = runtil + 1

                if debug:
                    print 'RUNTIL: %d' % runtil
                iterobj.set_line_offset(min(offset + (tabwidth-ralign) - motion, runtil-1))
            else:
                iterobj.set_line_offset(offset + (tabwidth-ralign) - motion)

        # do the placement
        if shift or both:   # as long as shift is being used...
            doc.select_range(iterobj, selecto)  # don't break the selection!
        else:
            doc.place_cursor(iterobj)
        #return True    # TODO: shouldn't this work ?
        return False    # TODO: however this does!

# ex:ts=4:et:
