"""Run a disposable-account, zero-value StudioNet example.

Commands: deploy | inspect TX | wait TX | register CASE | review CASE | read CASE
Cases: good, batched, missing. Set .local/contract.address after deployment.
"""
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from eth_account import Account
from genlayer_py.client import GenLayerClient
from genlayer_py.chains import studionet
from genlayer_py.provider import GenLayerProvider
from genlayer_py.abi import calldata
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


ROOT = Path(__file__).resolve().parents[1]
LOCAL, EVIDENCE = ROOT / ".local", ROOT / "evidence"
LOCAL.mkdir(exist_ok=True)
EVIDENCE.mkdir(exist_ok=True)
REPO = "mrcactus66/benchmark-pair"
CONDITIONS = ["RasterSet r2, RGB 1024x1024 resized to 256x256 with bilinear interpolation",
              "Exactly one CPU thread and no GPU", "Request batch size is 1"]
key_file = LOCAL / "studio.key"
if not key_file.exists():
    key_file.write_text(Account.create().key.hex(), encoding="ascii")
account = Account.from_key(key_file.read_text(encoding="ascii"))


class StudioProvider(GenLayerProvider):
    def __init__(self, url):
        super().__init__(url)
        self.session = requests.Session()
        self.session.mount("https://", HTTPAdapter(max_retries=Retry(
            total=2, connect=2, read=0, backoff_factor=1)))

    def make_request(self, method, params):
        response = self.session.post(self.url, json={"jsonrpc": "2.0", "id": 1,
            "method": method, "params": params}, timeout=30)
        response.raise_for_status()
        value = response.json()
        self._raise_on_error(value, method)
        return value


client = GenLayerClient(studionet, account)
client.provider = StudioProvider(studionet.rpc_urls["default"]["http"][0])
client.w3.provider = client.provider
client.initialize_consensus_smart_contract()


def save(name, value):
    (EVIDENCE / name).write_text(json.dumps(value, indent=2, default=str) + "\n", encoding="utf-8", newline="\n")


def log(operation, tx):
    save(operation + "-transaction.json", {"network": "StudioNet", "chain_id": 61999,
        "transaction_id": tx, "demo_account": account.address})
    print(tx, flush=True)


def execution(row):
    return {key: row.get(key) for key in ("mode", "vote", "execution_result",
        "genvm_result", "nondet_disagree", "contract_state_hash")}


command = sys.argv[1]
if command == "deploy":
    code = (ROOT / "contracts/benchmark_pair.py").read_bytes()
    tx = client.deploy_contract(code, args=[REPO], leader_only=False)
    log("deploy", tx)
    save("source.json", {"repository": REPO, "fixtures": "synthetic",
        "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "contract_sha256": hashlib.sha256(code).hexdigest()})
elif command in ("inspect", "wait"):
    tx = sys.argv[2]
    raw = (client.wait_for_transaction_receipt(tx, interval=3000, retries=12, full_transaction=True)
           if command == "wait" else client.get_transaction(tx))
    raw_dir = LOCAL / "raw-receipts"
    raw_dir.mkdir(exist_ok=True)
    (raw_dir / (tx + ".json")).write_text(json.dumps(raw, indent=2, default=str), encoding="utf-8")
    public = {key: raw.get(key) for key in ("hash", "from_address", "to_address", "value",
        "type", "status_name", "result_name", "leader_only", "rotation_count", "num_of_rounds", "last_round")}
    public["explorer"] = "https://explorer-studio.genlayer.com/tx/" + tx
    public["executions"] = [execution(r) for r in raw["consensus_data"]["leader_receipt"] + raw["consensus_data"]["validators"]]
    encoded = raw["data"]["calldata"]
    public["calldata"] = encoded.get("readable") if isinstance(encoded, dict) else calldata.decode(base64.b64decode(encoded))
    if raw["type"] == 1:
        public["deployed_source_sha256"] = hashlib.sha256(base64.b64decode(raw["data"]["contract_code"])).hexdigest()
        assert public["deployed_source_sha256"] == hashlib.sha256((ROOT / "contracts/benchmark_pair.py").read_bytes()).hexdigest()
        if raw["result_name"] == "MAJORITY_AGREE":
            (LOCAL / "contract.address").write_text(raw["to_address"], encoding="ascii")
    save(tx + "-receipt.json", public)
    print(json.dumps({k: v for k, v in public.items() if k in (
        "hash", "to_address", "status_name", "result_name", "rotation_count")}, indent=2))
elif command in ("register", "review", "read"):
    case = sys.argv[2]
    contract = (LOCAL / "contract.address").read_text().strip()
    if command == "register":
        commit = json.loads((EVIDENCE / "source.json").read_text())["commit"]
        sources = []
        for filename in ("baseline.txt", "candidate-" + case + ".txt"):
            sources.append({"url": "https://raw.githubusercontent.com/" + REPO + "/" + commit + "/examples/" + filename,
                "sha256": hashlib.sha256((ROOT / "examples" / filename).read_bytes()).hexdigest()})
        args = [case, "Cedar v1", "Cedar v2", json.dumps(CONDITIONS), 100, 2000, json.dumps(sources)]
        save(case + "-input.json", {"contract": contract, "method": "register", "args": args})
        log(case + "-register", client.write_contract(contract, "register", args=args, value=0, leader_only=False))
    elif command == "review":
        log(case + "-review", client.write_contract(contract, "review", args=[case], value=0, leader_only=False))
    else:
        result = json.loads(client.read_contract(contract, "get_review", args=[case]))
        save(case + "-onchain.json", result)
        print(json.dumps({k: v for k, v in result.items() if k != "reports"}, indent=2))
else:
    raise SystemExit("Unknown command")
