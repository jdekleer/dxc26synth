import pandas as pd

import time

from ExampleDiagnosisSystem import ExampleDiagnosisSystem

## Create diagnosis system class

# Create diagnosis system. 
EDS = ExampleDiagnosisSystem() # change to your class here

## Initialize diagnosis system
# The diagnosis system parameter file is created by calling EDS.Train()
# You can initialize the diagnosis system by loading a parameter file
EDS.Initialize()

# Load test data
test_data = pd.read_csv('../data/trainingdata/wltp_f_waf_110.csv')

# Log diagnosis output
filehandler = open('../results/output.csv', 'w')
filehandler.write('sample_time,computation_time,detection,fpic_rank,fpim_rank,fwaf_rank,fiml_rank,fx_rank\n');

for time_idx in range(len(test_data)):
    t = time.time()

    # Feed sample to diagnosis system and return diagnosis output
    detection, isolation = EDS.Input(test_data.iloc[time_idx,:].to_frame().transpose())
    
    elapsed = time.time() - t
    
    # Log diagnosis output
    filehandler.write('%f,%f,%d,%f,%f,%f,%f,%f \n' % (test_data['time'][time_idx], elapsed, detection[0], isolation[0,0], isolation[0,1], isolation[0,2], isolation[0,3], isolation[0,4]))

    # Print progress
    if time_idx % 1000 == 0:
        print('.', end="")
    
# Close logger
filehandler.close()