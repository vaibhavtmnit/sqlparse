import re
with open('src/miner/miner_tools.py', 'r', encoding='utf-8') as f:
    content = f.read()

new_content = """    def clean_workspace_files(self):
        \"\"\"
        Cleans the workspace by removing all files inside the output and state directories, 
        but keeps the directories themselves intact.
        \"\"\"
        from pathlib import Path
        dirs_to_clean = [
            self.root + "/mining/output",
            self.root + "/mining/state"
        ]
        
        for d in dirs_to_clean:
            dir_path = Path(d)
            if dir_path.exists() and dir_path.is_dir():
                for file_path in dir_path.rglob('*'):
                    if file_path.is_file():
                        try:
                            file_path.unlink()
                        except:
                            pass
        logger.info("Workspace files cleaned (directories retained).")
"""

pattern = r"    def clean_workspace_files\(self\):.*?logger\.info\(\"Workspace files cleaned \(directories retained\)\.\"\)\n"

modified_content = re.sub(pattern, new_content, content, flags=re.DOTALL)

with open('src/miner/miner_tools.py', 'w', encoding='utf-8') as f:
    f.write(modified_content)
print("Regex patch applied.")
