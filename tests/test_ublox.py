#
# Tests for the UBX message decoding used by the serial panel.
#

import struct

import pytest

from dronecan_gui_tool.panels.serial_panel import UBloxAttrDict, UBloxDescriptor, UBloxError, UBloxMessage

CLASS_TEST = 0x01
MSG_TEST = 0x30

REC_FORMAT = '<BBh'
REC_FIELDS = ['chn', 'svid', 'cno']
RECORDS = [(1, 5, 40), (2, 7, -33)]


def make_message(payload):
    msg = UBloxMessage()
    msg.pack_message(CLASS_TEST, MSG_TEST, payload)
    return msg


def pack_records(records):
    return b''.join(struct.pack(REC_FORMAT, *r) for r in records)


@pytest.fixture
def counted_descriptor():
    '''descriptor whose number of records is given by the numCh field'''
    return UBloxDescriptor('TEST_COUNTED', '<IBBH', ['iTOW', 'numCh', 'flags', 'reserved'],
                           'numCh', REC_FORMAT, REC_FIELDS)


@pytest.fixture
def remaining_descriptor():
    '''descriptor whose number of records is derived from the remaining payload length'''
    return UBloxDescriptor('TEST_REMAINING', '<I', ['iTOW'],
                           '_remaining', REC_FORMAT, REC_FIELDS)


def test_attr_dict_item_and_attribute_access():
    r = UBloxAttrDict()
    r['svid'] = 5
    r.cno = 40
    assert r.svid == 5
    assert r['cno'] == 40
    assert r == {'svid': 5, 'cno': 40}


def test_attr_dict_missing_attribute_raises_attribute_error():
    r = UBloxAttrDict()
    with pytest.raises(AttributeError):
        r.missing
    assert getattr(r, 'missing', None) is None


def test_unpack_counted_records(counted_descriptor):
    payload = struct.pack('<IBBH', 1234, len(RECORDS), 0, 0) + pack_records(RECORDS)
    msg = make_message(payload)

    counted_descriptor.unpack(msg)

    assert msg.iTOW == 1234
    assert msg.numCh == len(RECORDS)
    assert len(msg.recs) == len(RECORDS)
    for rec, expected in zip(msg.recs, RECORDS):
        assert isinstance(rec, UBloxAttrDict)
        assert dict(rec) == dict(zip(REC_FIELDS, expected))
    assert msg.recs[1].svid == 7


def test_unpack_remaining_records(remaining_descriptor):
    payload = struct.pack('<I', 1234) + pack_records(RECORDS)
    msg = make_message(payload)

    remaining_descriptor.unpack(msg)

    assert msg.iTOW == 1234
    assert [tuple(r[f] for f in REC_FIELDS) for r in msg.recs] == RECORDS


def test_unpack_remaining_with_no_records(remaining_descriptor):
    msg = make_message(struct.pack('<I', 1234))

    remaining_descriptor.unpack(msg)

    assert msg.iTOW == 1234
    assert msg.recs == []


def test_unpack_extra_bytes_raises(counted_descriptor):
    payload = struct.pack('<IBBH', 1234, 1, 0, 0) + pack_records(RECORDS)
    msg = make_message(payload)

    with pytest.raises(UBloxError):
        counted_descriptor.unpack(msg)


def test_unpack_truncated_record_raises(counted_descriptor):
    payload = struct.pack('<IBBH', 1234, 3, 0, 0) + pack_records(RECORDS)
    msg = make_message(payload)

    with pytest.raises(UBloxError):
        counted_descriptor.unpack(msg)


def test_format_includes_records(counted_descriptor):
    payload = struct.pack('<IBBH', 1234, len(RECORDS), 0, 0) + pack_records(RECORDS)
    msg = make_message(payload)

    text = counted_descriptor.format(msg)

    assert text.startswith('TEST_COUNTED: iTOW=1234, numCh=2')
    assert '[ chn=1, svid=5, cno=40 ]' in text
    assert '[ chn=2, svid=7, cno=-33 ]' in text


def test_pack_unpack_round_trip(counted_descriptor):
    payload = struct.pack('<IBBH', 1234, len(RECORDS), 0, 0) + pack_records(RECORDS)
    original = make_message(payload)
    counted_descriptor.unpack(original)

    counted_descriptor.pack(original)
    repacked = UBloxMessage()
    repacked._buf = bytearray(original._buf)
    counted_descriptor.unpack(repacked)

    assert bytes(original._buf) == bytes(make_message(payload)._buf)
    assert repacked._fields == original._fields
    assert repacked.recs == original.recs
