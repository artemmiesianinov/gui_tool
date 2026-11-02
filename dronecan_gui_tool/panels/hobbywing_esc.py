#
# Copyright (C) 2023  UAVCAN Development Team  <dronecan.org>
#
# This software is distributed under the terms of the MIT License.
#
# Author: Andrew Tridgell
#

import dronecan
from functools import partial
from PyQt6.QtWidgets import QVBoxLayout, QWidget, QLabel, QDialog, \
    QPlainTextEdit, QPushButton, QLineEdit, QFileDialog, QComboBox, QHBoxLayout, QSpinBox, QMessageBox
from PyQt6.QtCore import QTimer, Qt
from logging import getLogger
from ..widgets import make_icon_button, get_icon, get_monospace_font
from ..widgets import table_display
import random
import base64
import struct

__all__ = 'PANEL_NAME', 'spawn', 'get_icon'

PANEL_NAME = 'Hobbywing ESC Panel'

logger = getLogger(__name__)

_singleton = None

MSG_ID_STATUS1 = 20050
MSG_ID_STATUS2 = 20051
MSG_ID_STATUS3 = 20052

# 'Dir (status)' is the live direction flag from StatusMsg1, 'Dir (config)' is what the ESC reports when queried
COLUMNS = ['Node', 'ThrottleID', 'RPM', 'Voltage', 'Current', 'Temperature', 'Dir (status)', 'Dir (config)', 'Source',
           'Msg1 Hz', 'Msg2 Hz', 'Msg3 Hz', 'MOS °C', 'Cap °C', 'Motor °C']
RATE_COLUMNS = {MSG_ID_STATUS1: 'Msg1 Hz', MSG_ID_STATUS2: 'Msg2 Hz', MSG_ID_STATUS3: 'Msg3 Hz'}

# how often the settings of every ESC are read back for the table, in units of the 500 ms poll
CONFIG_POLL_PERIOD = 10

def rate_codes():
    '''map of reporting rate in Hz to SetReportingFrequency rate code'''
    req = dronecan.com.hobbywing.esc.SetReportingFrequency.Request()
    return {
        500 : req.RATE_500HZ,
        250 : req.RATE_250HZ,
        200 : req.RATE_200HZ,
        100 : req.RATE_100HZ,
        50 : req.RATE_50HZ,
        20 : req.RATE_20HZ,
        10 : req.RATE_10HZ,
        1 : req.RATE_1HZ,
        0 : req.RATE_0HZ,
    }

class HobbywingPanel(QDialog):
    DEFAULT_INTERVAL = 0.1

    def __init__(self, parent, node):
        super(HobbywingPanel, self).__init__(parent)
        self.setWindowTitle('Hobbywing ESC Panel')
        self.setAttribute(Qt.WA_DeleteOnClose)              # This is required to stop background timers!

        self._node = node
        self.node_map = {}
        self._selected_node = None
        self._poll_count = 0

        layout = QVBoxLayout()

        self.table = table_display.TableDisplay(COLUMNS)
        self.table.itemSelectionChanged.connect(self.on_selection_changed)
        layout.addWidget(self.table)

        self.baudrate = QComboBox(self)
        for b in [50000, 100000, 200000, 250000, 500000, 1000000]:
            self.baudrate.addItem(str(b))
        self.baudrate.setCurrentText(str(1000000))
        self.baudrate_set = QPushButton('Set', self)
        self.baudrate_set.clicked.connect(self.on_baudrate_set)
        
        layout.addLayout(self.labelWidget('Baudrate:', [self.baudrate, self.baudrate_set]))

        self.throttleid = QSpinBox(self)
        self.throttleid.setMinimum(1)
        self.throttleid.setMaximum(32)
        self.throttleid.setValue(1)
        self.throttleid_set = QPushButton('Set', self)
        self.throttleid_set.clicked.connect(self.on_throttleid_set)

        layout.addLayout(self.labelWidget('ThrottleID:', [self.throttleid, self.throttleid_set]))

        self.nodeid = QSpinBox(self)
        self.nodeid.setMinimum(1)
        self.nodeid.setMaximum(127)
        self.nodeid.setValue(1)
        self.nodeid_set = QPushButton('Set', self)
        self.nodeid_set.clicked.connect(self.on_nodeid_set)
        
        layout.addLayout(self.labelWidget('NodeID:', [self.nodeid, self.nodeid_set]))

        self.direction = QComboBox(self)
        self.direction.addItem("CW")
        self.direction.addItem("CCW")
        self.direction.setCurrentText("CW")
        self.direction_set = QPushButton('Set', self)
        self.direction_set.clicked.connect(self.on_direction_set)
        
        layout.addLayout(self.labelWidget('Direction:', [self.direction, self.direction_set]))

        self.msg1rate = QComboBox(self)
        for r in [0, 1, 10, 20, 50, 100, 200, 250, 500]:
            self.msg1rate.addItem(str(r))
        self.msg1rate.setCurrentText("50")
        self.msg1rate_set = QPushButton('Set', self)
        self.msg1rate_set.clicked.connect(self.on_msg1rate_set)
        
        layout.addLayout(self.labelWidget('Msg1Rate:', [self.msg1rate, self.msg1rate_set]))

        self.msg2rate = QComboBox(self)
        for r in [0, 1, 10, 20, 50, 100, 200, 250, 500]:
            self.msg2rate.addItem(str(r))
        self.msg2rate.setCurrentText("10")
        self.msg2rate_set = QPushButton('Set', self)
        self.msg2rate_set.clicked.connect(self.on_msg2rate_set)
        
        layout.addLayout(self.labelWidget('Msg2Rate:', [self.msg2rate, self.msg2rate_set]))

        self.msg3rate = QComboBox(self)
        for r in [0, 1, 10, 20, 50, 100, 200, 250, 500]:
            self.msg3rate.addItem(str(r))
        self.msg3rate.setCurrentText("10")
        self.msg3rate_set = QPushButton('Set', self)
        self.msg3rate_set.clicked.connect(self.on_msg3rate_set)
        
        layout.addLayout(self.labelWidget('Msg3Rate:', [self.msg3rate, self.msg3rate_set]))

        self.rate_combos = {MSG_ID_STATUS1: self.msg1rate,
                            MSG_ID_STATUS2: self.msg2rate,
                            MSG_ID_STATUS3: self.msg3rate}

        self.throttle_source = QComboBox(self)
        self.throttle_source.addItem("---")
        self.throttle_source.addItem("PWM")
        self.throttle_source.addItem("CAN")
        self.throttle_source.setCurrentText("---")
        self.throttle_source_set = QPushButton('Set', self)
        self.throttle_source_set.clicked.connect(self.on_throttle_source_set)
        
        layout.addLayout(self.labelWidget('Throttle_source:', [self.throttle_source, self.throttle_source_set]))
        
        self.setLayout(layout)
        self.resize(1000, 450)

        self.handlers = [node.add_handler(dronecan.com.hobbywing.esc.StatusMsg1, self.handle_StatusMsg1),
                         node.add_handler(dronecan.com.hobbywing.esc.StatusMsg2, self.handle_StatusMsg2),
                         node.add_handler(dronecan.com.hobbywing.esc.StatusMsg3, self.handle_StatusMsg3),
                         node.add_handler(dronecan.com.hobbywing.esc.GetEscID, self.handle_GetEscID)]

        QTimer.singleShot(500, self.request_ids)


    def handle_reply(self, msg):
        '''handle a reply to a set, then read the settings back so the controls show what the ESC actually uses'''
        if msg is not None:
            print('REPLY: ', dronecan.to_yaml(msg))
            self.read_config(msg.transfer.source_node_id)
        else:
            print("No reply")

    def update_row(self, nodeid, **values):
        '''update table cells of an ESC, keyed by column name'''
        data = self.table.get(nodeid)
        if data is None:
            data = [nodeid] + ['-'] * (len(COLUMNS) - 1)
        for name, value in values.items():
            data[COLUMNS.index(name)] = value
        self.table.update(nodeid, data)

    def handle_GetMajorConfig_reply(self, msg):
        '''handle a reply to the periodic GetMajorConfig poll'''
        if msg is None:
            # request timed out, e.g. the ESC is busy or offline; the next poll will retry
            return
        self.update_row(msg.transfer.source_node_id, Source=self.throttle_source_name(msg))
        # only fill in an unknown throttle source, so the poll doesn't overwrite a selection that is about to be set
        if self.throttle_source.currentText() == "---":
            self.handle_throttle_source_reply(msg)

    @staticmethod
    def throttle_source_name(msg):
        return "CAN" if msg.response.throttle_source == 0 else "PWM"

    def handle_throttle_source_reply(self, msg):
        '''show the throttle source from a GetMajorConfig reply'''
        if msg is None:
            return
        nodeid = msg.transfer.source_node_id
        self.update_row(nodeid, Source=self.throttle_source_name(msg))
        if nodeid == self._selected_node:
            self.throttle_source.setCurrentText(self.throttle_source_name(msg))

    def handle_direction_reply(self, msg):
        '''show the direction reported by an ESC'''
        if msg is None:
            print("No reply to direction query")
            return
        direction = msg.response.direction
        if direction not in (0, 1):
            return
        nodeid = msg.transfer.source_node_id
        name = "CW" if direction == 0 else "CCW"
        self.update_row(nodeid, **{'Dir (config)': name})
        if nodeid == self._selected_node:
            self.direction.setCurrentText(name)

    def handle_rate_reply(self, msg):
        '''show a reporting rate reported by an ESC'''
        if msg is None:
            print("No reply to reporting rate query")
            return
        hz = {code: hz for hz, code in rate_codes().items()}.get(msg.response.rate)
        column = RATE_COLUMNS.get(msg.response.MSG_ID)
        if hz is None or column is None:
            return
        nodeid = msg.transfer.source_node_id
        self.update_row(nodeid, **{column: hz})
        if nodeid == self._selected_node:
            self.rate_combos[msg.response.MSG_ID].setCurrentText(str(hz))

    def read_config(self, nodeid):
        '''ask an ESC for its current settings; the replies update its table row, and the controls if it is selected'''
        hw = dronecan.com.hobbywing.esc
        requests = []

        req = hw.GetMajorConfig.Request()
        req.option = 0
        requests.append((req, self.handle_throttle_source_reply))

        req = hw.SetDirection.Request()
        req.direction = req.DIRECTION_QUERY
        requests.append((req, self.handle_direction_reply))

        for msgid in self.rate_combos:
            req = hw.SetReportingFrequency.Request()
            req.option = req.OPTION_READ
            req.MSG_ID = msgid
            requests.append((req, self.handle_rate_reply))

        # space the requests out a little rather than flooding the ESC with them at once
        for i, (req, callback) in enumerate(requests):
            QTimer.singleShot(50 * i, partial(self._node.request, req, nodeid, callback))

    def on_selection_changed(self):
        '''show the settings of the newly selected ESC'''
        nodeid = self.table.get_selected()
        if nodeid == self._selected_node:
            return
        self._selected_node = nodeid
        if nodeid is None:
            return
        self.nodeid.setValue(nodeid)
        if nodeid in self.node_map:
            self.throttleid.setValue(int(self.node_map[nodeid]))
        self.throttle_source.setCurrentText("---")
        self.read_config(nodeid)

    def selected_esc(self):
        '''the node ID of the selected ESC, or None after telling the user to select one'''
        nodeid = self.table.get_selected()
        if nodeid is None:
            QMessageBox.warning(self, PANEL_NAME, 'Select an ESC in the table first.')
        return nodeid

    def on_throttleid_set(self):
        '''set throttle ID'''
        nodeid = self.selected_esc()
        if nodeid is None:
            return
        req = dronecan.com.hobbywing.esc.SetID.Request()
        req.node_id = nodeid
        req.throttle_channel = int(self.throttleid.value())
        self._node.request(req, nodeid, self.handle_reply)

    def on_nodeid_set(self):
        '''set node ID'''
        nodeid = self.selected_esc()
        if nodeid is None:
            return
        if nodeid not in self.node_map:
            QMessageBox.warning(self, PANEL_NAME, 'The throttle ID of this ESC is not known yet, try again shortly.')
            return
        thr_id = int(self.node_map[nodeid])
        req = dronecan.com.hobbywing.esc.SetID.Request()
        req.node_id = int(self.nodeid.value())
        req.throttle_channel = thr_id
        self._node.request(req, nodeid, self.handle_reply)
        
    def on_baudrate_set(self):
        '''set baudrate'''
        nodeid = self.selected_esc()
        if nodeid is None:
            return
        req = dronecan.com.hobbywing.esc.SetBaud.Request()
        bmap = {
            1000000 : req.BAUD_1MBPS,
            500000 : req.BAUD_500KBPS,
            250000 : req.BAUD_250KBPS,
            200000 : req.BAUD_200KBPS,
            100000 : req.BAUD_100KBPS,
            50000 : req.BAUD_50KBPS,
        }
        baudrate = int(self.baudrate.currentText())
        req.baud = bmap[baudrate]
        self._node.request(req, nodeid, self.handle_reply)

    def on_direction_set(self):
        '''set direction'''
        nodeid = self.selected_esc()
        if nodeid is None:
            return
        req = dronecan.com.hobbywing.esc.SetDirection.Request()
        req.direction = 0 if self.direction.currentText() == "CW" else 1
        self._node.request(req, nodeid, self.handle_reply)

    def on_throttle_source_set(self):
        '''set throttle source'''
        nodeid = self.selected_esc()
        if nodeid is None:
            return
        req = dronecan.com.hobbywing.esc.SetThrottleSource.Request()
        txt = self.throttle_source.currentText()
        if txt == "---":
            return
        req.source = 0 if txt == "CAN" else 1
        self._node.request(req, nodeid, self.handle_reply)

    def set_rate(self, nodeid, msgid, rate):
        '''set a message rate'''
        req = dronecan.com.hobbywing.esc.SetReportingFrequency.Request()
        req.option = req.OPTION_WRITE
        req.MSG_ID = msgid
        rmap = rate_codes()
        if not rate in rmap:
            print("Invalid rate %d - must be one of %s" % (rate, ','.join(map(str, rmap.keys()))))
            return
        req.rate = rmap[rate]
        self._node.request(req, nodeid, self.handle_reply)

    def on_rate_set(self, msgid):
        '''set the reporting rate of a status message from its combo box'''
        nodeid = self.selected_esc()
        if nodeid is None:
            return
        self.set_rate(nodeid, msgid, int(self.rate_combos[msgid].currentText()))

    def on_msg1rate_set(self):
        '''set msg1 rate'''
        self.on_rate_set(MSG_ID_STATUS1)

    def on_msg2rate_set(self):
        '''set msg2 rate'''
        self.on_rate_set(MSG_ID_STATUS2)

    def on_msg3rate_set(self):
        '''set msg3 rate'''
        self.on_rate_set(MSG_ID_STATUS3)
        
    def handle_GetEscID(self, msg):
        '''handle GetEscID'''
        nodeid = msg.transfer.source_node_id
        if len(msg.message.payload) != 2:
            return
        is_new = nodeid not in self.node_map
        self.node_map[nodeid] = msg.message.payload[1]
        self.update_row(nodeid, ThrottleID=msg.message.payload[1])
        if is_new:
            self.read_config(nodeid)

    def handle_StatusMsg1(self, msg):
        '''handle StatusMsg1'''
        self.update_row(msg.transfer.source_node_id,
                        RPM=msg.message.rpm,
                        **{'Dir (status)': "CCW" if msg.message.status & (1<<14) else "CW"})

    def handle_StatusMsg2(self, msg):
        '''handle StatusMsg2'''
        self.update_row(msg.transfer.source_node_id,
                        Voltage="%.2f" % (msg.message.input_voltage*0.1),
                        Current="%.2f" % (msg.message.current*0.1),
                        Temperature=msg.message.temperature)

    def handle_StatusMsg3(self, msg):
        '''handle StatusMsg3'''
        self.update_row(msg.transfer.source_node_id,
                        **{'MOS °C': msg.message.MOS_T,
                           'Cap °C': msg.message.CAP_T,
                           'Motor °C': msg.message.Motor_T})

    def request_ids(self):
        '''call GetEscID'''
        QTimer.singleShot(500, self.request_ids)
        req = dronecan.com.hobbywing.esc.GetEscID()
        req.payload = [0]
        self._node.broadcast(req)
        # for IDs we have, send GetMajorConfig
        for nodeid in self.node_map.keys():
            req = dronecan.com.hobbywing.esc.GetMajorConfig.Request()
            req.option = 0
            self._node.request(req, nodeid, self.handle_GetMajorConfig_reply)
        # every few seconds read back the other settings of every ESC as well, staggered so they don't all go at once
        self._poll_count += 1
        if self._poll_count % CONFIG_POLL_PERIOD == 0:
            for i, nodeid in enumerate(list(self.node_map.keys())):
                QTimer.singleShot(100 * i, partial(self.read_config, nodeid))

        
    def labelWidget(self, label, widgets):
        '''a widget with a label'''
        hlayout = QHBoxLayout()
        hlayout.addWidget(QLabel(label, self))
        if not isinstance(widgets, list):
            widgets = [widgets]
        for w in widgets:
            hlayout.addWidget(w)
        return hlayout

    def __del__(self):
        for h in self.handlers:
            h.remove()
        global _singleton
        _singleton = None

    def closeEvent(self, event):
        super(HobbywingPanel, self).closeEvent(event)
        self.__del__()


def spawn(parent, node):
    global _singleton
    if _singleton is None:
        try:
            _singleton = HobbywingPanel(parent, node)
        except Exception as ex:
            print(ex)

    _singleton.show()
    _singleton.raise_()
    _singleton.activateWindow()

    return _singleton


get_icon = partial(get_icon, 'fa6s.asterisk')
