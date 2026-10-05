cd /opt/flowed
scripts/new-user.sh e2e-bench4
python3 scripts/flowed-profile.py e2e-bench4 --name Test --native Catalan --target English --level A1 --goal A2
scripts/flowed-web.sh --stop --port 4199
scripts/flowed-web.sh --app --port 4199 e2e-bench4
python3 scripts/flowed-tutorbench.py run --port 4199 --name qwen3-27b-4060 --host llvm-4060ti e2e-bench4 --repeat 3
