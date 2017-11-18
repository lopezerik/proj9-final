import nose
import arrow
from ftc import *
# Classes are written assuming sorted order.
# Any tests here follow sorted ordering.

def test_all():
    ##################################################
    # Basic Test: Merge 2 events, calc free time     #
    ##################################################
    appt1start = arrow.get("2017-11-10T13:00:00-08:00")
    appt1end = arrow.get("2017-11-10T14:00:00-08:00")
    appt1 = TimeBlock(appt1start, appt1end, "APPT1")

    appt2start = arrow.get("2017-11-10T13:30:00-08:00")
    appt2end = arrow.get("2017-11-10T15:00:00-08:00")
    appt2 = TimeBlock(appt2start, appt2end, "APPT2")

    masterstart = arrow.get("1970-01-01T00:00:00-08:00")
    masterend = arrow.get("1970-01-01T10:00:00-08:00")
    master = TimeBlock(masterstart, masterend, "master")
    master.initMaster(appt1)
    
    master.merge(appt2)
    assert(str(master.disjointSet[0].start) == "2017-11-10T13:00:00-08:00")
    assert(str(master.disjointSet[0].end) == "2017-11-10T15:00:00-08:00")
    
    freestart = arrow.get("2017-11-10T14:00:00-08:00")
    freeend = arrow.get("2017-11-10T19:00:00-08:00")
    free = FreeBlock(freestart, freeend)
    free.calcFree(master)
    assert(str(free.disjointSet[0].start) == "2017-11-10T15:00:00-08:00")
    assert(str(free.disjointSet[0].end) == "2017-11-10T19:00:00-08:00")

def test_more():
    ##################################################
    # Basic Test: Merge 2 events, calc free time     #
    ##################################################
    appt1start = arrow.get("2017-11-10T13:00:00-08:00")
    appt1end = arrow.get("2017-11-10T14:00:00-08:00")
    appt1 = TimeBlock(appt1start, appt1end, "APPT1")

    appt2start = arrow.get("2017-11-10T13:30:00-08:00")
    appt2end = arrow.get("2017-11-10T15:00:00-08:00")
    appt2 = TimeBlock(appt2start, appt2end, "APPT2")

    masterstart = arrow.get("1970-01-01T00:00:00-08:00")
    masterend = arrow.get("1970-01-01T10:00:00-08:00")
    master = TimeBlock(masterstart, masterend, "master")
    master.initMaster(appt1)
    
    master.merge(appt2)
    ###################################################
    # Basic Test: Merge another event, calc free time #
    ###################################################
    appt3start = arrow.get("2017-11-10T15:00:00-08:00")
    appt3end = arrow.get("2017-11-10T16:00:00-08:00")
    appt3 = TimeBlock(appt3start, appt3end, "APPT3")
    
    master.merge(appt3)
    assert(str(master.disjointSet[0].start) == "2017-11-10T13:00:00-08:00")
    assert(str(master.disjointSet[0].end) == "2017-11-10T16:00:00-08:00")

    freestart = arrow.get("2017-11-10T14:00:00-08:00")
    freeend = arrow.get("2017-11-10T19:00:00-08:00")
    free = FreeBlock(freestart, freeend)
    free.calcFree(master)
    assert(str(free.disjointSet[0].start) == "2017-11-10T16:00:00-08:00")
    assert(str(free.disjointSet[0].end) == "2017-11-10T19:00:00-08:00")

def testSplit():
    ##################################################
    # Basic Test: Merge 3 split events, calc free time     #
    ##################################################
    appt1start = arrow.get("2017-11-10T13:00:00-08:00")
    appt1end = arrow.get("2017-11-10T14:00:00-08:00")
    appt1 = TimeBlock(appt1start, appt1end, "APPT1")

    appt2start = arrow.get("2017-11-10T15:00:00-08:00")
    appt2end = arrow.get("2017-11-10T16:00:00-08:00")
    appt2 = TimeBlock(appt2start, appt2end, "APPT2")

    appt3start = arrow.get("2017-11-10T17:00:00-08:00")
    appt3end = arrow.get("2017-11-10T18:00:00-08:00")
    appt3 = TimeBlock(appt3start, appt3end, "APPT3")

    masterstart = arrow.get("1970-01-01T00:00:00-08:00")
    masterend = arrow.get("1970-01-01T10:00:00-08:00")
    master = TimeBlock(masterstart, masterend, "master")
    master.initMaster(appt1)
    
    master.merge(appt2)
    master.merge(appt3)
    assert(str(master.disjointSet[0].start) == "2017-11-10T13:00:00-08:00")
    assert(str(master.disjointSet[0].end) == "2017-11-10T14:00:00-08:00")
    assert(str(master.disjointSet[1].start) == "2017-11-10T15:00:00-08:00")
    assert(str(master.disjointSet[1].end) == "2017-11-10T16:00:00-08:00")
    assert(str(master.disjointSet[2].start) == "2017-11-10T17:00:00-08:00")
    assert(str(master.disjointSet[2].end) == "2017-11-10T18:00:00-08:00")

    freestart = arrow.get("2017-11-10T14:00:00-08:00")
    freeend = arrow.get("2017-11-10T19:00:00-08:00")
    free = FreeBlock(freestart, freeend)
    free.calcFree(master)
    assert(str(free.disjointSet[0].start) == "2017-11-10T14:00:00-08:00")
    assert(str(free.disjointSet[0].end) == "2017-11-10T15:00:00-08:00")
    assert(str(free.disjointSet[1].start) == "2017-11-10T16:00:00-08:00")
    assert(str(free.disjointSet[1].end) == "2017-11-10T17:00:00-08:00")
    assert(str(free.disjointSet[2].start) == "2017-11-10T18:00:00-08:00")
    assert(str(free.disjointSet[2].end) == "2017-11-10T19:00:00-08:00")

def testNone():
    ##################################################
    # Test busy block that blocks all free time      #
    ###################################################

    appt1start = arrow.get("2017-11-10T13:00:00-08:00")
    appt1end = arrow.get("2017-11-10T16:00:00-08:00")
    appt1 = TimeBlock(appt1start, appt1end, "APPT1")

    masterstart = arrow.get("1970-01-01T00:00:00-08:00")
    masterend = arrow.get("1970-01-01T10:00:00-08:00")
    master = TimeBlock(masterstart, masterend, "master")
    master.initMaster(appt1)

    freestart = arrow.get("2017-11-10T14:00:00-08:00")
    freeend = arrow.get("2017-11-10T15:00:00-08:00")
    free = FreeBlock(freestart, freeend)
    free.calcFree(master)

    assert(free.empty)
