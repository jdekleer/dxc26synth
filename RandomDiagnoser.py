import random
from DiagnosisSystemClass import DiagnosisSystemClass

class RandomDiagnoser(DiagnosisSystemClass):
    """A baseline diagnoser that always detects a fault and returns a random gate."""
    
    def __init__(self):
        super().__init__()
    
    def Input(self, sample, timeout=None, start_time=None):
        """Always detect and return a random gate as isolation."""
        # Always report detection
        detection = True
        
        # Return a random gate as isolation
        if self.gates:
            random_gate = random.choice(self.gates)[0]  # gates is list of (name, type, inputs, output)
            isolation = {random_gate}
        else:
            isolation = set()
        
        return (detection, isolation)


class NullDiagnoser(DiagnosisSystemClass):
    """A baseline diagnoser that always reports nothing wrong."""
    
    def __init__(self):
        super().__init__()
    
    def Input(self, sample, timeout=None, start_time=None):
        """Always report no detection and empty isolation."""
        return (False, set())


class WorstDiagnoser(DiagnosisSystemClass):
    """A diagnoser that returns a single diagnosis claiming ALL gates are faulty.
    
    This should score near 0 because it has maximum false positives.
    Returns AG format (set of frozensets) directly.
    """
    
    def __init__(self):
        super().__init__()
    
    def Input(self, sample, timeout=None, start_time=None):
        """Always detect and return a single diagnosis with ALL gates faulty."""
        detection = True
        # Return a SINGLE diagnosis with all gates (AG format)
        all_gates = frozenset(gate[0] for gate in self.gates)
        isolation = {all_gates}  # Set containing one frozenset
        return (detection, isolation)

