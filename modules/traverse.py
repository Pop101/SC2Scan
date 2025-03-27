def traverse(self, *nodes):
    # For getting the value at a path in a dict of dicts (json)
    
    if self is None:
        return None
    
    if nodes[0] in self:
        if len(nodes) == 1:
            return self[nodes[0]]
        else:
            return traverse(self[nodes[0]], *nodes[1:])
    else:
        return None