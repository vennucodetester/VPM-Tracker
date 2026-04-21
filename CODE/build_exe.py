import PyInstaller.__main__
import os
import shutil

def build():
    print("Building VPM Tracker...")
    
    # Clean previous builds
    if os.path.exists('dist'):
        shutil.rmtree('dist')
    if os.path.exists('build'):
        shutil.rmtree('build')

    PyInstaller.__main__.run([
        'vpm_tracker/tracker_app.py',  # Entry point
        '--name=VPM_Tracker',          # Name of the executable
        '--noconsole',                 # Hide the console window
        '--onedir',                    # Create a directory (easier for debugging/assets)
        '--clean',                     # Clean cache
        # Add any necessary hidden imports if PyInstaller misses them
        '--hidden-import=PyQt6',
        '--hidden-import=vpm_tracker.ui.tree_grid_view',
        '--hidden-import=vpm_tracker.models.task_node',
        '--hidden-import=vpm_tracker.utils.workday_calculator',
        '--hidden-import=vpm_tracker.utils.config_manager',
    ])

    print("\nBuild Complete!")
    print(f"Executable is located at: {os.path.abspath('dist/VPM_Tracker/VPM_Tracker.exe')}")

if __name__ == "__main__":
    build()
