from pyasl.batch import BatchEngine, BatchJob
import os

print("cwd =", os.getcwd())
print(
    os.path.abspath("pyasl/data/human_single_delay")
)
print(
    os.path.exists("pyasl/data/human_single_delay")  
)
def main():
    jobs = [
        BatchJob(
            data_dir="pyasl/data/human_single_delay",  # .img
            config_path="pyasl/configs/testmti.yaml",
            )
    ]

    engine = BatchEngine(max_workers=1)
    results = engine.run(jobs)

    print(results)

if __name__ == "__main__":
    main()
    
    
#  BatchJob  
#   ↓
# BatchEngine
#   ↓
# ProcessPoolExecutor
#   ↓
# batch_worker
#   ↓
# run_pipeline