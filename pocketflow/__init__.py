# pocketflow/__init__.py
import asyncio, warnings, copy, time

class BaseNode:
    def __init__(self): self.params,self.successors={},{}
    def set_params(self,params): self.params=params
    def add_successor(self,node,action="default"):
        if action in self.successors: warnings.warn(f"Overwriting successor for action '{action}'")
        self.successors[action]=node;return node
    def prep(self,shared): pass
    def exec(self,prep_res): pass
    def post(self,shared,prep_res,exec_res): pass
    def _exec(self,prep_res): return self.exec(prep_res)
    def _run(self,shared): p=self.prep(shared);e=self._exec(p);return self.post(shared,p,e)
    def run(self,shared):
        if self.successors: warnings.warn("Node won't run successors. Use Flow.")
        return self._run(shared)
    def __rshift__(self,other): return self.add_successor(other)
    def __sub__(self,action):
        if isinstance(action,str): return _ConditionalTransition(self,action)
        raise TypeError("Action must be a string")

class _ConditionalTransition:
    def __init__(self,src,action): self.src,self.action=src,action
    def __rshift__(self,tgt): return self.src.add_successor(tgt,self.action)

class Node(BaseNode):
    def __init__(self,max_retries=1,wait=0): super().__init__();self.max_retries,self.wait=max_retries,wait; self.cur_retry=0 # Initialize cur_retry
    def exec_fallback(self,prep_res,exc): raise exc
    def _exec(self,prep_res):
        for self.cur_retry in range(self.max_retries):
            try: return self.exec(prep_res)
            except Exception as e:
                if self.cur_retry==self.max_retries-1:
                    # Log the final failure before fallback
                    # In a real app, use proper logging
                    print(f"Node {type(self).__name__}: Max retries ({self.max_retries}) reached. Failing with exception: {e}. Executing fallback.")
                    return self.exec_fallback(prep_res,e)
                print(f"Node {type(self).__name__}: Retry {self.cur_retry + 1}/{self.max_retries} failed with exception: {e}. Waiting {self.wait}s.")
                if self.wait>0: time.sleep(self.wait)

class BatchNode(Node):
    # Override _exec to handle items individually with retries/fallback per item
    def _exec(self,items):
        results = []
        items_iterable = items or []
        for item in items_iterable:
            # We call the single-item execution logic (Node._exec) for each item
            # This ensures retries and fallback are handled per item.
            item_result = super(BatchNode, self)._exec(item)
            results.append(item_result)
        return results

class Flow(BaseNode):
    def __init__(self,start): super().__init__();self.start=start
    def get_next_node(self,curr,action):
        nxt=curr.successors.get(action or "default")
        if not nxt and curr.successors: warnings.warn(f"Flow ends: Action '{action or 'default'}' not found in successors {list(curr.successors.keys())} for node {type(curr).__name__}")
        return nxt
    def _orch(self,shared,params=None):
        curr,p=copy.copy(self.start),(params or {**self.params})
        while curr:
            curr.set_params(p)
            print(f"Flow: Running node {type(curr).__name__}") # Basic logging
            c=curr._run(shared)
            print(f"Flow: Node {type(curr).__name__} finished, returned action: {c}") # Basic logging
            curr=copy.copy(self.get_next_node(curr,c))
    def _run(self,shared):
        print(f"Flow {type(self).__name__}: Starting run.")
        pr=self.prep(shared) # Flow prep
        self._orch(shared)   # Orchestrate nodes
        print(f"Flow {type(self).__name__}: Orchestration complete.")
        return self.post(shared,pr,None) # Flow post
    def exec(self,prep_res): raise RuntimeError("Flow can't exec.")

class BatchFlow(Flow):
    def _run(self,shared):
        pr=self.prep(shared) or []
        print(f"BatchFlow {type(self).__name__}: Preparing to run for {len(pr)} batch parameters.")
        for i, bp in enumerate(pr):
            print(f"BatchFlow {type(self).__name__}: Running batch item {i+1}/{len(pr)} with params {bp}")
            self._orch(shared,{**self.params,**bp})
        print(f"BatchFlow {type(self).__name__}: All batch items processed.")
        return self.post(shared,pr,None)

# --- Async Classes (Not used in this project, but part of the framework) ---
class AsyncNode(Node):
    def prep(self,shared): raise RuntimeError("Use prep_async.")
    def exec(self,prep_res): raise RuntimeError("Use exec_async.")
    def post(self,shared,prep_res,exec_res): raise RuntimeError("Use post_async.")
    def exec_fallback(self,prep_res,exc): raise RuntimeError("Use exec_fallback_async.")
    def _run(self,shared): raise RuntimeError("Use run_async.")
    async def prep_async(self,shared): pass
    async def exec_async(self,prep_res): pass
    async def exec_fallback_async(self,prep_res,exc): raise exc
    async def post_async(self,shared,prep_res,exec_res): pass
    async def _exec(self,prep_res):
        for self.cur_retry in range(self.max_retries):
            try: return await self.exec_async(prep_res)
            except Exception as e:
                if self.cur_retry==self.max_retries-1: return await self.exec_fallback_async(prep_res,e)
                if self.wait>0: await asyncio.sleep(self.wait)
    async def run_async(self,shared):
        if self.successors: warnings.warn("Node won't run successors. Use AsyncFlow.")
        return await self._run_async(shared)
    async def _run_async(self,shared): p=await self.prep_async(shared);e=await self._exec(p);return await self.post_async(shared,p,e)

class AsyncBatchNode(AsyncNode,BatchNode):
     # Override _exec to handle items individually with async retries/fallback per item
    async def _exec(self,items):
        results = []
        items_iterable = items or []
        for item in items_iterable:
            # Call the single-item async execution logic (AsyncNode._exec) for each item.
            item_result = await super(AsyncBatchNode, self)._exec(item)
            results.append(item_result)
        return results

class AsyncParallelBatchNode(AsyncNode,BatchNode):
    async def _exec(self,items):
        items_iterable = items or []
        # Gather results of running single-item async execution logic in parallel
        tasks = [super(AsyncParallelBatchNode,self)._exec(i) for i in items_iterable]
        return await asyncio.gather(*tasks)

class AsyncFlow(Flow,AsyncNode):
    async def _orch_async(self,shared,params=None):
        curr,p=copy.copy(self.start),(params or {**self.params})
        while curr:
            curr.set_params(p)
            print(f"AsyncFlow: Running node {type(curr).__name__}") # Basic logging
            if isinstance(curr,AsyncNode):
                c=await curr._run_async(shared)
            else: # Allow mixing sync/async nodes in AsyncFlow
                 c=curr._run(shared)
            print(f"AsyncFlow: Node {type(curr).__name__} finished, returned action: {c}") # Basic logging
            curr=copy.copy(self.get_next_node(curr,c))
    async def _run_async(self,shared):
        print(f"AsyncFlow {type(self).__name__}: Starting run.")
        p=await self.prep_async(shared)
        await self._orch_async(shared)
        print(f"AsyncFlow {type(self).__name__}: Orchestration complete.")
        return await self.post_async(shared,p,None)

class AsyncBatchFlow(AsyncFlow,BatchFlow):
    async def _run_async(self,shared):
        pr=await self.prep_async(shared) or []
        print(f"AsyncBatchFlow {type(self).__name__}: Preparing to run for {len(pr)} batch parameters.")
        for i, bp in enumerate(pr):
            print(f"AsyncBatchFlow {type(self).__name__}: Running batch item {i+1}/{len(pr)} with params {bp}")
            await self._orch_async(shared,{**self.params,**bp})
        print(f"AsyncBatchFlow {type(self).__name__}: All batch items processed.")
        return await self.post_async(shared,pr,None)

class AsyncParallelBatchFlow(AsyncFlow,BatchFlow):
    async def _run_async(self,shared):
        pr=await self.prep_async(shared) or []
        print(f"AsyncParallelBatchFlow {type(self).__name__}: Preparing to run {len(pr)} batch items in parallel.")
        tasks = [self._orch_async(shared,{**self.params,**bp}) for bp in pr]
        await asyncio.gather(*tasks)
        print(f"AsyncParallelBatchFlow {type(self).__name__}: All parallel batch items processed.")
        return await self.post_async(shared,pr,None)