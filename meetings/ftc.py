import arrow

# All methods assume that you are passing in the events sorted from earliest to latests.
# Google Calendar API can give you the events in sorted order so this is not a big issue.

class TimeBlock:
    
    def __init__(self, begin, end, summ):
        self.start = arrow.get(begin)
        self.end = arrow.get(end)
        self.summary = summ
        self.disjointSet = []
        self.mergeIndex = -1;
        self.redundant = False
        return
    
    def __str__(self):
        return self.summary + " " + self.start.format("MM-DD-YYYY") + " " + self.end.format("MM-DD-YYYY")

    def initMaster(self, other):
        self.disjointSet.append(other)
        return

    def overlaps(self, other):
        # check all from disjointSet
        i = 0
        for block in self.disjointSet:
            if(other.start >= block.start and other.end <= block.end):
                # block is redundant
                self.redundant = True
                return False
            if((other.start < block.start) and (other.end >= block.start)):
                self.mergeIndex = i;
                return True
            if((other.end > block.end) and (other.start <= block.end)):
                self.mergeIndex = i;
                return True
            i+=1
        return False
    
    def merge(self, other):
        if(self.overlaps(other)):
            # merge the blocks
            block = self.disjointSet[self.mergeIndex]
            if(other.start < block.start):
                self.disjointSet[self.mergeIndex].start = other.start
            else:
                self.disjointSet[self.mergeIndex].end = other.end
            
            self.mergeIndex = -1
        elif(not self.redundant):
            # add to set only if it is not a redundant event
            self.disjointSet.append(other)
            self.redundant = False
        
        return

class FreeBlock:
    
    def __init__(self, start, end):
        self.start = start
        self.end = end
        self.empty = False
        self.disjointSet = []
        return
    
    # Very important that masterBlock be sorted or algorithm will not work.
    def calcFree(self, masterBlock):
        currStart = self.start
        currEnd = self.end
        calName = "Free Block"
        # loop through blocks in masterblock
        for block in masterBlock.disjointSet:
            calName = block.summary
            if(block.start < currStart and block.end > currEnd):
                # block takes up all free time, done searching, no free time available
                self.empty = True;
                return
            elif(block.start <= currStart):
                # block starts before our freeblock, or at the same time
                currStart = block.end
            elif(block.end >= currEnd):
                # block ends after our freeblock, or at the same time
                currEnd = block.start
            elif(block.start > currStart and block.end < currEnd):
                # we need to split the set up
                old = TimeBlock(currStart, block.start, block.summary)
                self.disjointSet.append(old)
                currStart = block.end
            
        main = TimeBlock(currStart, currEnd, calName)
        self.disjointSet.append(main)
        
