# A2.3 消费者 cli 正式包 v1



review_kind: PACKAGE_REVIEW；PENDING_NEW_PACKAGE_REVIEW，未派发。

真人本段/有限适配授权保留；worker sol/medium，fresh reviewer sol/xhigh，有效后台 UNKNOWN。

完整原始义务以 task-v3.md/requirements-v3.json/node-bindings-v3.json 为准：119项、112独立运行；core selfcheck 不作为全阶段接受。

先读真实停止的 core-api-bindings-v1.json 及完整源/局部证据，再读原A2/安全/接口/验收/历史缺陷。

独占 owner `a23-cli-r1-20261005`，证据 `artifacts/workflow/A2.3-receipts-20261004/cli_config-r1/`。

仅以下精确路径可写，其他所有候选/正式控制文件/Git只读；不新开子agent。

- `src/agent_guard/gateway/receipt_config.py`

- `src/agent_guard/gateway/receipt_worker.py`

- `tests/unit/test_receipt_worker_config.py`

- `tests/integration/test_receipt_worker_process.py`



各建独立 owner/fullID PG16+LinuxPy3.11/sourcecopy/noneditablewheel/cache/HOME/随机TEST gateway与独立downstream DB/CA/ports/PIDs。清普通DSN，仅本轮显式TEST目标；不读取/连接peer资源或3个既有容器。只清实际成功创建、fullID/label核实的自有资源。

并行测试 source-copy/wheel 从 controller/consumer-common-baseline-v1（root在全部消费者派发前冻结）的完整不可变树建立，只覆盖自己的4或3精确文件；不得从并行中的main工作区重新copy/安装而消费peer半成品。共享core15+全部其它依赖用共同baseline SHA核实；main里peer3/4文件属于明确并行写区，不作为本worker只读依赖。根最终按7-path union核完整scope，其他候选/HEAD/index都不准改变。

局部有限节点/案例/断言如下；原命名若需因真实API改变，保全语义/有限案例并交actual collected nodeids/source assertion/raw evidence映射，不删减每组10round原竞态或真实PID故障。局部union不证明整个父项，G1/G2全局完整整合和fresh验收保留。

```json

[
  {
    "node_binding_id": "N005",
    "kind": "planned_test",
    "planned_file": "tests/integration/test_receipt_worker_process.py",
    "planned_function": "test_real_sigkill_between_signature_and_commit",
    "sole_initial_owner": "a23-cli-r1-20261005",
    "phase": "cli_config",
    "status": "PLANNED_NOT_IMPLEMENTED_NOT_COLLECTED_NOT_RUN",
    "parameter_case_contract": {
      "case_labels": [
        "actual_receipt_worker_SIGN_PGWAIT_SIGKILL_RESTART"
      ],
      "not_cartesian": true,
      "future_actual_parameters": "Bind implemented exact parameterized nodes after native stop; labels express local semantic cases, not invented argument names.",
      "allocation": "Case labels/explicit value sets are local finite obligations, not automatic cross products. Actual implemented collected nodeids/assertion lines/run evidence mandatory later."
    },
    "local_assertions": [
      {
        "id": "N005.A1",
        "text": "After core API freeze, actual python -m agent_guard.gateway.receipt_worker PID completes real sign then observed PG target wait; SIGKILL before commit."
      },
      {
        "id": "N005.A2",
        "text": "New CLI PID on same PG recovers durable PENDING/null to same material/id/iat; no finally recovery or business reexecution; complete publication effect oracle."
      }
    ],
    "actual_source_lines": null,
    "actual_collected_nodeids": [],
    "required_final_execution": "sole integrator and fresh reviewer separately source + noneditable wheel after all native stop/exclusive transfer; not initial owner proof of global closure",
    "finite_case_inputs": {
      "signal": 9,
      "entry": "actual python -m agent_guard.gateway.receipt_worker PID after core frozen/fresh consumer review",
      "window": "sign complete PGwait before commit then distinct new PID restart"
    },
    "case_values_status": "PROPOSED_FINITE_VALUES_NOT_ACTUAL_PARAMETERS_NOT_RUN"
  },
  {
    "node_binding_id": "N006",
    "kind": "planned_test",
    "planned_file": "tests/integration/test_receipt_worker_process.py",
    "planned_function": "test_real_commit_reply_loss_recovers_original_jws",
    "sole_initial_owner": "a23-cli-r1-20261005",
    "phase": "cli_config",
    "status": "PLANNED_NOT_IMPLEMENTED_NOT_COLLECTED_NOT_RUN",
    "parameter_case_contract": {
      "case_labels": [
        "actual_receipt_worker_COMMIT_OBSERVED_REPLYLOSS_RESTART"
      ],
      "not_cartesian": true,
      "future_actual_parameters": "Bind implemented exact parameterized nodes after native stop; labels express local semantic cases, not invented argument names.",
      "allocation": "Case labels/explicit value sets are local finite obligations, not automatic cross products. Actual implemented collected nodeids/assertion lines/run evidence mandatory later."
    },
    "local_assertions": [
      {
        "id": "N006.A1",
        "text": "Separate connection observes READY before actual CLI stdout/IPC delivery loss or kill."
      },
      {
        "id": "N006.A2",
        "text": "New CLI PID returns exact committed JWS/signed_at without re-sign/business effects; full immutable/three-field oracle."
      }
    ],
    "actual_source_lines": null,
    "actual_collected_nodeids": [],
    "required_final_execution": "sole integrator and fresh reviewer separately source + noneditable wheel after all native stop/exclusive transfer; not initial owner proof of global closure",
    "finite_case_inputs": {
      "entry": "actual receipt_worker CLI PID",
      "window": "independent conn observes committed READY before real IPC/stdout loss or kill; new PID returns saved bytes"
    },
    "case_values_status": "PROPOSED_FINITE_VALUES_NOT_ACTUAL_PARAMETERS_NOT_RUN"
  },
  {
    "node_binding_id": "N009",
    "kind": "planned_test",
    "planned_file": "tests/unit/test_receipt_worker_config.py",
    "planned_function": "test_gateway_key_role_spki_kid_and_public_match",
    "sole_initial_owner": "a23-cli-r1-20261005",
    "phase": "cli_config",
    "status": "PLANNED_NOT_IMPLEMENTED_NOT_COLLECTED_NOT_RUN",
    "parameter_case_contract": {
      "case_labels": [
        "AS_SPKI_reuse",
        "holder_SPKI_reuse",
        "new_gateway_kid_role_conflict",
        "wrong_private_public_match",
        "unknown_kid",
        "valid_distinct_signer"
      ],
      "not_cartesian": true,
      "future_actual_parameters": "Bind implemented exact parameterized nodes after native stop; labels express local semantic cases, not invented argument names.",
      "allocation": "Case labels/explicit value sets are local finite obligations, not automatic cross products. Actual implemented collected nodeids/assertion lines/run evidence mandatory later."
    },
    "local_assertions": [
      {
        "id": "N009.A1",
        "text": "Compare canonical SPKI and signing roles, fail missing/mismatched keys and new gateway kid collisions; preserve legal cross-operation holder tuple aliases."
      },
      {
        "id": "N009.A2",
        "text": "Config loader receives only needed operator data; does not copy AS/holder/downstream secrets. HTTP private-key isolation is separately integration/inspection bound."
      }
    ],
    "actual_source_lines": null,
    "actual_collected_nodeids": [],
    "required_final_execution": "sole integrator and fresh reviewer separately source + noneditable wheel after all native stop/exclusive transfer; not initial owner proof of global closure",
    "finite_case_inputs": {
      "key_cases": [
        "valid distinct GW",
        "same AS canonical SPKI",
        "same holder canonical SPKI",
        "new GW kid equals AS role kid",
        "independent wrong public key",
        "missing kid"
      ],
      "legal_alias_control": {
        "operations": [
          {
            "tenant": "tenant-a23-A",
            "client": "client-a23-A"
          },
          {
            "tenant": "tenant-a23-B",
            "client": "client-a23-B"
          }
        ],
        "shared_holder": {
          "DID": "did:web:identity.agent-guard.test:shared-holder",
          "kid": "did:web:identity.agent-guard.test:shared-holder#key-1",
          "SPKI": "same actual generated public SPKI"
        },
        "roots": "two independent actual AS roots; unique actor DIDs inside each valid chain",
        "cases": [
          "forward_SUCCEEDED_sequential",
          "reverse_FAILED_sequential",
          "forward_concurrent_10",
          "reverse_concurrent_10",
          "wrong_exact_tuple tenantA/clientB",
          "wrong_SPKI actually different SM2 key",
          "queryB using ownerA proof"
        ],
        "oracle": "legal both publish/query/offline; bad trust503 proof rollback repair same proof200 replay409; crossowner403, no global kid uniqueness"
      }
    },
    "case_values_status": "PROPOSED_FINITE_VALUES_NOT_ACTUAL_PARAMETERS_NOT_RUN"
  },
  {
    "node_binding_id": "N010",
    "kind": "planned_test",
    "planned_file": "tests/unit/test_receipt_worker_config.py",
    "planned_function": "test_init_private_paths_modes_umask_exclusive_old_config_preserved",
    "sole_initial_owner": "a23-cli-r1-20261005",
    "phase": "cli_config",
    "status": "PLANNED_NOT_IMPLEMENTED_NOT_COLLECTED_NOT_RUN",
    "parameter_case_contract": {
      "case_labels": [
        "existing_target",
        "file_or_parent_symlink",
        "FIFO",
        "socket",
        "directory",
        "unsafe_ancestor",
        "umask_0000",
        "umask_0022",
        "umask_0077",
        "umask_0777",
        "relative_secret_reference"
      ],
      "not_cartesian": true,
      "future_actual_parameters": "Bind implemented exact parameterized nodes after native stop; labels express local semantic cases, not invented argument names.",
      "allocation": "Case labels/explicit value sets are local finite obligations, not automatic cross products. Actual implemented collected nodeids/assertion lines/run evidence mandatory later."
    },
    "local_assertions": [
      {
        "id": "N010.A1",
        "text": "Descriptor-bound private_files exclusive creation produces new 0700 directory/0600 synthetic CSPRNG SM2 PEM and config/public copy; never overwrite/change old input."
      },
      {
        "id": "N010.A2",
        "text": "Reject unsafe paths and occupied targets; preserve old bytes and safely absolute-reference relative secret without reading/copying it; safe partial failure. Actual two-process contention belongs process node."
      }
    ],
    "actual_source_lines": null,
    "actual_collected_nodeids": [],
    "required_final_execution": "sole integrator and fresh reviewer separately source + noneditable wheel after all native stop/exclusive transfer; not initial owner proof of global closure",
    "finite_case_inputs": {
      "umasks": [
        "0000",
        "0022",
        "0077",
        "0777"
      ],
      "types": [
        "existing file",
        "file symlink",
        "parent symlink",
        "FIFO",
        "socket",
        "directory",
        "unsafe ancestor"
      ],
      "new_modes": [
        "0700",
        "0600"
      ],
      "relative_reference": "../old-private/downstream.json safely absolute-reference without opening/copying secret"
    },
    "case_values_status": "PROPOSED_FINITE_VALUES_NOT_ACTUAL_PARAMETERS_NOT_RUN"
  },
  {
    "node_binding_id": "N027",
    "kind": "planned_test",
    "planned_file": "tests/integration/test_receipt_worker_process.py",
    "planned_function": "test_continuous_cli_bounded_bad_row_fairness_and_restart",
    "sole_initial_owner": "a23-cli-r1-20261005",
    "phase": "cli_config",
    "status": "PLANNED_NOT_IMPLEMENTED_NOT_COLLECTED_NOT_RUN",
    "parameter_case_contract": {
      "case_labels": [
        "missing_AG_RECEIPT_DATABASE_URL",
        "ordinary_DSN_no_fallback",
        "check_offline",
        "run_loader",
        "bounds_bool_zero_negative_overmax",
        "bad_row_keyset_rotation",
        "actual_restart",
        "two_init_processes"
      ],
      "not_cartesian": true,
      "future_actual_parameters": "Bind implemented exact parameterized nodes after native stop; labels express local semantic cases, not invented argument names.",
      "allocation": "Case labels/explicit value sets are local finite obligations, not automatic cross products. Actual implemented collected nodeids/assertion lines/run evidence mandatory later."
    },
    "local_assertions": [
      {
        "id": "N027.A1",
        "text": "Actual CLI check/run share strict private loader; check opens no DB, missing explicit AG_RECEIPT_DATABASE_URL fails without ordinary DSN/provision/migration/reset."
      },
      {
        "id": "N027.A2",
        "text": "Exact positive integer bounds connect1..30/lock1..60000/statement1..60000/batch1..256/poll100..60000; bool/zero/negative/overmax reject; bounded keyset rotation reaches legal pending beyond bad row."
      },
      {
        "id": "N027.A3",
        "text": "Actual owned restart and competing init PIDs exit cleanly, one exclusive initializer; old bytes preserved, safe permissions/error redaction, no raw/DSN/secret disclosure. Public route refusal is HTTPS node obligation."
      }
    ],
    "actual_source_lines": null,
    "actual_collected_nodeids": [],
    "required_final_execution": "sole integrator and fresh reviewer separately source + noneditable wheel after all native stop/exclusive transfer; not initial owner proof of global closure",
    "finite_case_inputs": {
      "connect": [
        1,
        5,
        30,
        0,
        -1,
        31,
        true
      ],
      "lock": [
        1,
        10000,
        60000,
        0,
        -1,
        60001,
        true
      ],
      "statement": [
        1,
        15000,
        60000,
        0,
        -1,
        60001,
        true
      ],
      "batch": [
        1,
        32,
        256,
        0,
        -1,
        257,
        true
      ],
      "poll": [
        100,
        1000,
        60000,
        99,
        -1,
        60001,
        true
      ],
      "fairness": "batch1 corrupt first then2 actual valid pending rows; bounded keyset advances/wraps",
      "init_PIDs": 2,
      "DSN": "unset AG_RECEIPT_DATABASE_URL fails without ordinary fallback"
    },
    "case_values_status": "PROPOSED_FINITE_VALUES_NOT_ACTUAL_PARAMETERS_NOT_RUN"
  },
  {
    "node_binding_id": "N034",
    "kind": "planned_test",
    "planned_file": "tests/integration/test_receipt_worker_process.py",
    "planned_function": "test_installed_wheel_cli_parent_child_provenance_and_readme",
    "sole_initial_owner": "a23-cli-r1-20261005",
    "phase": "cli_config",
    "status": "PLANNED_NOT_IMPLEMENTED_NOT_COLLECTED_NOT_RUN",
    "parameter_case_contract": {
      "case_labels": [
        "source_CLI_parent_child",
        "noneditable_wheel_CLI_parent_child",
        "new_init_check_run_fragment"
      ],
      "not_cartesian": true,
      "future_actual_parameters": "Bind implemented exact parameterized nodes after native stop; labels express local semantic cases, not invented argument names.",
      "allocation": "Case labels/explicit value sets are local finite obligations, not automatic cross products. Actual implemented collected nodeids/assertion lines/run evidence mandatory later."
    },
    "local_assertions": [
      {
        "id": "N034.A1",
        "text": "Own CLI parent/worker child report actual module file/metadata; no src shadow in noneditable wheel; init/check/run documented fragment actually executed."
      },
      {
        "id": "N034.A2",
        "text": "Function does not independently prove full suite/A1/B regressions, all14SQL inventory or historical README AS/GW closure; these are integrator evidence bindings."
      }
    ],
    "actual_source_lines": null,
    "actual_collected_nodeids": [],
    "required_final_execution": "sole integrator and fresh reviewer separately source + noneditable wheel after all native stop/exclusive transfer; not initial owner proof of global closure",
    "finite_case_inputs": {
      "installs": [
        "source Linux UID501 Python3.11",
        "noneditablewheel Linux UID501 Python3.11"
      ],
      "entry": "actual CLI init/check/run parent+workerchild",
      "provenance": [
        "module file",
        "distribution metadata",
        "no src shadow"
      ],
      "whole_regression": "G1 separate"
    },
    "case_values_status": "PROPOSED_FINITE_VALUES_NOT_ACTUAL_PARAMETERS_NOT_RUN"
  },
  {
    "node_binding_id": "N036",
    "kind": "planned_test",
    "planned_file": "tests/integration/test_receipt_worker_process.py",
    "planned_function": "test_owned_child_processes_exit_and_test_target_marker",
    "sole_initial_owner": "a23-cli-r1-20261005",
    "phase": "cli_config",
    "status": "PLANNED_NOT_IMPLEMENTED_NOT_COLLECTED_NOT_RUN",
    "parameter_case_contract": {
      "case_labels": [
        "owned_child_exit",
        "explicit_test_target_no_fallback"
      ],
      "not_cartesian": true,
      "future_actual_parameters": "Bind implemented exact parameterized nodes after native stop; labels express local semantic cases, not invented argument names.",
      "allocation": "Case labels/explicit value sets are local finite obligations, not automatic cross products. Actual implemented collected nodeids/assertion lines/run evidence mandatory later."
    },
    "local_assertions": [
      {
        "id": "N036.A1",
        "text": "Actual test-owned CLI child PIDs exit, target marker and explicit TEST DSN guard verified without ordinary fallback."
      },
      {
        "id": "N036.A2",
        "text": "Does not claim all other worker/reviewer/container resource inventories or global freeze; those bind separate controller native evidence."
      }
    ],
    "actual_source_lines": null,
    "actual_collected_nodeids": [],
    "required_final_execution": "sole integrator and fresh reviewer separately source + noneditable wheel after all native stop/exclusive transfer; not initial owner proof of global closure",
    "finite_case_inputs": {
      "resources": "actual successfully created owned CLI child PID+provenance",
      "target": "explicit owned TEST DSN marker, no ordinary fallback",
      "all_other_resources": "G2 separate"
    },
    "case_values_status": "PROPOSED_FINITE_VALUES_NOT_ACTUAL_PARAMETERS_NOT_RUN"
  }
]

```



完整局部 source+非editablewheel实跑、质量/受影响旧回归/真PID与TLS/全部ag及DS oracle，自有实际 command/exit/pass-fail-error-skip/完整日志/JUnit/SHA；保留首次失败/补正原件。

交完整 implementation.md、API/源SHA、local binding、command/raw manifests、开始结束readonly Git/scope/子PID/资源清理核验。所有 wrapper 真退出、无owned资源余留后原生 STOP，READY_FOR_INTEGRATION；不是 ACCEPTED。不修改共享core、正式包、SQL/锁/依赖/CI；范围必要变化先 NEEDS_REPLAN 停写。

全部STOP后sole integrator联合新CLI+HTTPS、完整119/112及所有历史/P01–21/30goal边界sourcewheel，再fresh完整独立验收。最新真人要求完整A2验收和A3规划完成后停止，本次A3只规划、不实施。

CLI专项：init/check/run严格descriptor-bound private_files和exact schema；check与run同loader，check不连DB；run只AG_RECEIPT_DATABASE_URL，无普通fallback/provision/migrate/reset。init CSPRNG0700/0600不覆盖、旧config byte保持、safe绝对secrets_path但不读/复制secret，newGWkid/SPKI角色隔离。bounded数字/batch keyset公平，坏材料不饿死后项、日志脱敏。实际receipt_worker PID两窗口sign→commit SIGKILL与commit→IPC/stdout回复丢失，独立conn证目标SQL/READY/newPID原JWS与signed_at。禁止生产ENV故障hook。
