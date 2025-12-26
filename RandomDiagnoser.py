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

