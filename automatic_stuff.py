import numpy as np 

def phase_assignment_greedy(grid: dict):
	'''
        each item has the foloowing:
        - 'power' (or 'cumPower')
		- name 
		- ....
	'''
	phases = [{'total_load': 0}, {'total_load': 0}, {'total_load': 0}]

	loads_unsorted = {key: value['power'].sum() for key, value in grid.items()}
	loads = dict(sorted(loads_unsorted.items(), key=lambda x:x[1], reverse=True))
	for key, value in loads.items():	
		assigned_phase = min(range(len(phases)), key=lambda i: phases[i]['total_load'])
		# grid[key]['assigned_phase'] = assigned_phase
		phases[assigned_phase]['total_load'] += value
		print(f'{key}: {value:.0f}W, phase {assigned_phase}')

	print(f'\ntotal on phases: {phases}')
	phaseBalance = 100*np.std(grid['generator']['cumPower']/np.mean(grid['generator']['cumPower']))
	print(f'balance : {phaseBalance:.1f}%')

	return loads
		
