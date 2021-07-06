
    import heapq
    class UnderKHeadp(object):
        def __init__(self,topK,keyFunc):
            self._data = []
            self.topK=topK
            self.keyFunc = keyFunc
        def push(self,item):
            if(len(self._data)<self.topK):
                heapq.heappush(self._data, (self.keyFunc(item), item))
            else:
                heapq.heappushpop(self._data, (self.keyFunc(item), item))
        def pop(self):
           return heapq.heappop(self._data)[1]
     
