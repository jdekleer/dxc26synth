import xml.etree.ElementTree as ET
from collections import defaultdict

class DiagnosisSystemClass:
    def __init__(self):
        self.modelFile = None
        self.inputs = []      # List of input port names
        self.outputs = []     # List of output port names
        self.gates = []       # Topologically sorted list of (gate_name, gate_type, [input_signals], output_signal)
        self.connections = {} # Maps wire/probe to connected signal
    
    def newModelFile(self, modelFile):
        self.modelFile = modelFile
        self._parseModel()
    
    def _parseModel(self):
        """Parse XML model file into intermediate representation for fast simulation."""
        tree = ET.parse(self.modelFile)
        root = tree.getroot()
        
        # Handle XML namespace
        ns = {'dx': 'urn:org:dx-competition:system'}
        
        # Find the system element
        system = root.find('.//dx:system', ns)
        if system is None:
            # Try without namespace
            system = root.find('.//system')
        
        # Parse components
        components = {}  # name -> type
        for comp in system.findall('.//dx:component', ns) or system.findall('.//component'):
            name = comp.find('dx:name', ns)
            if name is None:
                name = comp.find('name')
            ctype = comp.find('dx:componentType', ns)
            if ctype is None:
                ctype = comp.find('componentType')
            if name is not None and ctype is not None:
                components[name.text] = ctype.text
        
        # Parse connections
        conn_map = defaultdict(list)  # Maps each endpoint to its connected endpoints
        for conn in system.findall('.//dx:connection', ns) or system.findall('.//connection'):
            c1 = conn.find('dx:c1', ns)
            if c1 is None:
                c1 = conn.find('c1')
            c2 = conn.find('dx:c2', ns)
            if c2 is None:
                c2 = conn.find('c2')
            if c1 is not None and c2 is not None:
                conn_map[c1.text].append(c2.text)
                conn_map[c2.text].append(c1.text)
        
        # Identify inputs and outputs (ports)
        self.inputs = []
        self.outputs = []
        for name, ctype in components.items():
            if ctype == 'port':
                if name.startswith('i'):
                    self.inputs.append(name)
                elif name.startswith('o'):
                    self.outputs.append(name)
        
        # Sort inputs and outputs naturally
        self.inputs.sort(key=lambda x: (len(x), x))
        self.outputs.sort(key=lambda x: (len(x), x))
        
        # Build gate list with connections
        # Gate naming convention: gate10 has gate10.i1, gate10.i2, gate10.o
        gate_info = {}  # gate_name -> (type, [input_signals], output_signal)
        for name, ctype in components.items():
            if ctype in ['nand2', 'and2', 'or2', 'nor2', 'xor2', 'not1', 'buf1', 
                         'nand3', 'and3', 'or3', 'nor3', 'nand4', 'and4', 'or4', 'nor4',
                         'nand5', 'and5', 'or5', 'nor5', 'nand8', 'and8', 'and9', 'nor8',
                         'inverter', 'buffer']:
                # Find connected signals through wires
                gate_inputs = []
                gate_output = None
                
                # Find input wires (gate.i1, gate.i2, etc.)
                i = 1
                while f"{name}.i{i}" in components:
                    wire = f"{name}.i{i}"
                    # Find what this wire connects to
                    for connected in conn_map[wire]:
                        if connected != name:
                            # Resolve through probes if needed
                            gate_inputs.append(connected)
                            break
                    i += 1
                
                # Find output wire
                if f"{name}.o" in components:
                    wire = f"{name}.o"
                    for connected in conn_map[wire]:
                        if connected != name:
                            gate_output = connected
                            break
                
                gate_info[name] = (ctype, gate_inputs, gate_output)
        
        # Topological sort of gates based on dependencies
        self.gates = self._topologicalSort(gate_info)
    
    def _topologicalSort(self, gate_info):
        """Sort gates so dependencies are evaluated first."""
        # Build dependency graph
        output_to_gate = {}  # signal -> gate that produces it
        for gate_name, (gtype, inputs, output) in gate_info.items():
            if output:
                output_to_gate[output] = gate_name
        
        # Kahn's algorithm for topological sort
        in_degree = defaultdict(int)
        graph = defaultdict(list)
        
        for gate_name, (gtype, inputs, output) in gate_info.items():
            for inp in inputs:
                if inp in output_to_gate:
                    producer = output_to_gate[inp]
                    graph[producer].append(gate_name)
                    in_degree[gate_name] += 1
            if gate_name not in in_degree:
                in_degree[gate_name] = 0
        
        # Start with gates that have no dependencies
        queue = [g for g in gate_info if in_degree[g] == 0]
        sorted_gates = []
        
        while queue:
            gate = queue.pop(0)
            gtype, inputs, output = gate_info[gate]
            sorted_gates.append((gate, gtype, inputs, output))
            
            for dependent in graph[gate]:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)
        
        return sorted_gates
    
    def _computeGateOutput(self, gate_type, in_vals):
        """Compute gate output given gate type and input values."""
        if gate_type == 'nand2':
            return not (in_vals[0] and in_vals[1])
        elif gate_type == 'and2':
            return in_vals[0] and in_vals[1]
        elif gate_type == 'or2':
            return in_vals[0] or in_vals[1]
        elif gate_type == 'nor2':
            return not (in_vals[0] or in_vals[1])
        elif gate_type == 'xor2':
            return in_vals[0] != in_vals[1]
        elif gate_type in ['not1', 'inverter']:
            return not in_vals[0]
        elif gate_type in ['buf1', 'buffer']:
            return in_vals[0]
        elif gate_type.startswith('nand'):
            return not all(in_vals)
        elif gate_type.startswith('and'):
            return all(in_vals)
        elif gate_type.startswith('or'):
            return any(in_vals)
        elif gate_type.startswith('nor'):
            return not any(in_vals)
        else:
            return False  # Unknown gate type
    
    def simulate(self, inputs, faulty_gate=None, fault_value=None):
        """Simulate the circuit with given input values. 
        
        Args:
            inputs: dict of input signal values
            faulty_gate: optional gate name to inject fault
            fault_value: value to force for faulty gate output
            
        Returns dict of all signal values.
        """
        signals = dict(inputs)  # Start with input values
        
        for gate_name, gate_type, gate_inputs, gate_output in self.gates:
            if gate_output:
                if faulty_gate == gate_name:
                    # Inject fault - force output to fault_value
                    signals[gate_output] = fault_value
                else:
                    # Normal gate operation
                    in_vals = [signals.get(inp, False) for inp in gate_inputs]
                    signals[gate_output] = self._computeGateOutput(gate_type, in_vals)
        
        return signals
    
    def Initialize(self):
        pass
    
    def _checkConsistent(self, signals, sample):
        """Check if simulated signals are consistent with sample outputs."""
        for out in self.outputs:
            if out in sample and out in signals:
                # Only compare if we have both simulated and actual values
                simulated = signals[out]
                if simulated is not None and simulated != sample[out]:
                    return False
        return True
    
    def Input(self, sample, timeout=None, start_time=None):
        """Process a sample and return detection/isolation results.
        
        Args:
            sample: dict of sensor values
            timeout: optional timeout in seconds for this sample
            start_time: optional start time (from time.time()) for timeout checking
        """
        import time as time_module
        
        # Extract only input values from sample
        input_values = {inp: sample[inp] for inp in self.inputs if inp in sample}
        
        # Simulate the circuit with just the inputs (no fault)
        signals = self.simulate(input_values)
        
        # Check if outputs are consistent
        detection = not self._checkConsistent(signals, sample)
        
        # Isolation: if inconsistent, try every single fault
        isolation = set()
        
        if detection:
            for idx, (gate_name, gate_type, gate_inputs, gate_output) in enumerate(self.gates):
                # Check timeout periodically
                if timeout and start_time and idx % 100 == 0:
                    if time_module.time() - start_time > timeout:
                        break
                
                # Try fault_value = True
                signals_true = self.simulate(input_values, faulty_gate=gate_name, fault_value=True)
                if self._checkConsistent(signals_true, sample):
                    isolation.add(gate_name)
                    continue
                
                # Try fault_value = False
                signals_false = self.simulate(input_values, faulty_gate=gate_name, fault_value=False)
                if self._checkConsistent(signals_false, sample):
                    isolation.add(gate_name)
        
        return (detection, isolation)
