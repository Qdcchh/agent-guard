# A2.3 消费者 https 正式包 v1



review_kind: PACKAGE_REVIEW；PENDING_NEW_PACKAGE_REVIEW，未派发。

真人本段/有限适配授权保留；worker sol/medium，fresh reviewer sol/xhigh，有效后台 UNKNOWN。

完整原始义务以 task-v3.md/requirements-v3.json/node-bindings-v3.json 为准：119项、112独立运行；core selfcheck 不作为全阶段接受。

先读真实停止的 core-api-bindings-v1.json 及完整源/局部证据，再读原A2/安全/接口/验收/历史缺陷。

独占 owner `a23-https-r1-20261005`，证据 `artifacts/workflow/A2.3-receipts-20261004/https_fixture_demo-r1/`。

仅以下精确路径可写，其他所有候选/正式控制文件/Git只读；不新开子agent。

- `tests/fixtures/a23_https.py`

- `tests/integration/test_gateway_receipt_https.py`

- `tools/a2_receipt_demo.py`



各建独立 owner/fullID PG16+LinuxPy3.11/sourcecopy/noneditablewheel/cache/HOME/随机TEST gateway与独立downstream DB/CA/ports/PIDs。清普通DSN，仅本轮显式TEST目标；不读取/连接peer资源或3个既有容器。只清实际成功创建、fullID/label核实的自有资源。

并行测试 source-copy/wheel 从 controller/consumer-common-baseline-v1（root在全部消费者派发前冻结）的完整不可变树建立，只覆盖自己的4或3精确文件；不得从并行中的main工作区重新copy/安装而消费peer半成品。共享core15+全部其它依赖用共同baseline SHA核实；main里peer3/4文件属于明确并行写区，不作为本worker只读依赖。根最终按7-path union核完整scope，其他候选/HEAD/index都不准改变。

局部有限节点/案例/断言如下；原命名若需因真实API改变，保全语义/有限案例并交actual collected nodeids/source assertion/raw evidence映射，不删减每组10round原竞态或真实PID故障。局部union不证明整个父项，G1/G2全局完整整合和fresh验收保留。

```json

[
  {
    "node_binding_id": "N007",
    "kind": "planned_test",
    "planned_file": "tests/integration/test_gateway_receipt_https.py",
    "planned_function": "test_p21_https_login_consent_pkce_two_exchanges_four_tools_publish_query_offline",
    "sole_initial_owner": "a23-https-r1-20261005",
    "phase": "https_fixture_demo",
    "status": "PLANNED_NOT_IMPLEMENTED_NOT_COLLECTED_NOT_RUN",
    "parameter_case_contract": {
      "case_labels": [
        "single_CA_SAN_AS_GW_scene_four_canonical_tools"
      ],
      "not_cartesian": true,
      "future_actual_parameters": "Bind implemented exact parameterized nodes after native stop; labels express local semantic cases, not invented argument names.",
      "allocation": "Case labels/explicit value sets are local finite obligations, not automatic cross products. Actual implemented collected nodeids/assertion lines/run evidence mandatory later."
    },
    "local_assertions": [
      {
        "id": "N007.A1",
        "text": "Separate AS/GW processes with trusted CA and fixed SAN hostnames perform password/CSRF login, consent, exact state/nonce/redirect/S256, actual code proof exchange and RP IDToken verification."
      },
      {
        "id": "N007.A2",
        "text": "Two real AS exchanges use different Basic/SM2 holders for root→child→child; no synthetic root/direct mint."
      },
      {
        "id": "N007.A3",
        "text": "Positive tools exactly procurement.request.read, procurement.document.read, procurement.order.create, notification.template.send; tool_version is string 1; notification references a legal accessible existing operation."
      },
      {
        "id": "N007.A4",
        "text": "Each tool reaches actual independent downstream persistent terminal state, correct ancestor counters/effects, real publication/current fresh-proof query and independent offline SDK verification."
      },
      {
        "id": "N007.A5",
        "text": "notification.send and short aliases are refusal controls with all effect families zero-additional; source/wheel final runs are separate integrator obligations."
      }
    ],
    "actual_source_lines": null,
    "actual_collected_nodeids": [],
    "required_final_execution": "sole integrator and fresh reviewer separately source + noneditable wheel after all native stop/exclusive transfer; not initial owner proof of global closure",
    "finite_case_inputs": {
      "hosts": [
        "auth.agent-guard.test",
        "gateway.agent-guard.test"
      ],
      "tool_version": "1",
      "tools": [
        "procurement.request.read",
        "procurement.document.read",
        "procurement.order.create",
        "notification.template.send"
      ],
      "params": [
        {
          "request_id": "req-001"
        },
        {
          "request_id": "req-001",
          "document_id": "doc-001"
        },
        {
          "request_id": "req-001",
          "quote_id": "quote-001",
          "quote_version": "1",
          "items": [
            {
              "sku": "sku-001",
              "quantity": 1
            }
          ],
          "delivery_id": "office-001"
        },
        {
          "template_id": "order-created",
          "recipient_id": "user-demo-001",
          "operation_id": "actual accessible persistent prior operation ID"
        }
      ],
      "OIDC": "Actual network cookie jar: GET login CSRF→POST password→authorize exact registered redirect/state/nonce/S256 SHA256 verifier→consent/code→actual AGPoP code exchange→RP independent IDToken signature/iss/aud/exp/auth_time/nonce verify. Preserve actual Secure/HttpOnly/SameSite cookie policies. Two real AS exchanges use distinct Basic clients/SM2 keys root→child→child.",
      "closure": "One CA/SAN AS+GW multi-process scene, independent downstream persistent terminal, actual InternalPublisher/current fresh-proof query/independent operation-scoped ReceiptTrust offline; no historical TLS stitching",
      "aliases_negative_only": [
        "notification.send",
        "request.read",
        "document.read",
        "order.create"
      ]
    },
    "case_values_status": "PROPOSED_FINITE_VALUES_NOT_ACTUAL_PARAMETERS_NOT_RUN"
  },
  {
    "node_binding_id": "N028",
    "kind": "planned_test",
    "planned_file": "tests/integration/test_gateway_receipt_https.py",
    "planned_function": "test_wrong_ca_hostname_fixed_endpoint_refusals",
    "sole_initial_owner": "a23-https-r1-20261005",
    "phase": "https_fixture_demo",
    "status": "PLANNED_NOT_IMPLEMENTED_NOT_COLLECTED_NOT_RUN",
    "parameter_case_contract": {
      "case_labels": [
        "AS_wrong_CA",
        "GW_wrong_CA",
        "AS_wrong_SAN",
        "GW_wrong_SAN"
      ],
      "not_cartesian": true,
      "future_actual_parameters": "Bind implemented exact parameterized nodes after native stop; labels express local semantic cases, not invented argument names.",
      "allocation": "Case labels/explicit value sets are local finite obligations, not automatic cross products. Actual implemented collected nodeids/assertion lines/run evidence mandatory later."
    },
    "local_assertions": [
      {
        "id": "N028.A1",
        "text": "Actual TLS clients refuse wrong CA or fixed-hostname SAN for AS/GW processes; do not bypass verification or merge independent prior TLS evidence."
      },
      {
        "id": "N028.A2",
        "text": "No authorization/publication/query/business extra effects; full persisted oracle."
      }
    ],
    "actual_source_lines": null,
    "actual_collected_nodeids": [],
    "required_final_execution": "sole integrator and fresh reviewer separately source + noneditable wheel after all native stop/exclusive transfer; not initial owner proof of global closure",
    "finite_case_inputs": {
      "cases": [
        "AS wrong CA",
        "GW wrong CA",
        "AS wrong.agent-guard.test SAN",
        "GW wrong.agent-guard.test SAN"
      ],
      "positive_hosts": [
        "auth.agent-guard.test",
        "gateway.agent-guard.test"
      ]
    },
    "case_values_status": "PROPOSED_FINITE_VALUES_NOT_ACTUAL_PARAMETERS_NOT_RUN"
  },
  {
    "node_binding_id": "N029",
    "kind": "planned_test",
    "planned_file": "tests/integration/test_gateway_receipt_https.py",
    "planned_function": "test_https_stolen_token_tamper_replay_owner_revoke_zero_effects",
    "sole_initial_owner": "a23-https-r1-20261005",
    "phase": "https_fixture_demo",
    "status": "PLANNED_NOT_IMPLEMENTED_NOT_COLLECTED_NOT_RUN",
    "parameter_case_contract": {
      "case_labels": [
        "stolen_token",
        "parent_key_child_token",
        "body_tamper",
        "holder_tamper",
        "endpoint_tamper",
        "proof_replay",
        "cross_tenant_task_grant_holder_key",
        "ancestor_revoke_expiry_disable",
        "public_sign_recover_settle_routes"
      ],
      "not_cartesian": true,
      "future_actual_parameters": "Bind implemented exact parameterized nodes after native stop; labels express local semantic cases, not invented argument names.",
      "allocation": "Case labels/explicit value sets are local finite obligations, not automatic cross products. Actual implemented collected nodeids/assertion lines/run evidence mandatory later."
    },
    "local_assertions": [
      {
        "id": "N029.A1",
        "text": "True CA/SAN public AS/GW scene refuses each holder/body/endpoint/replay/cross-owner/current-revoke attack and unsigned public management route."
      },
      {
        "id": "N029.A2",
        "text": "Compare all ancestor/op/event/node/lease/outbox/evidence/proof/ds_* families against allowed baseline: zero unauthorized/duplicate effects."
      },
      {
        "id": "N029.A3",
        "text": "Public responses disclose no raw token/proof/evidence/private key/DSN/stack or other tenant data; positive canonical4 version1 scene supplies controls."
      }
    ],
    "actual_source_lines": null,
    "actual_collected_nodeids": [],
    "required_final_execution": "sole integrator and fresh reviewer separately source + noneditable wheel after all native stop/exclusive transfer; not initial owner proof of global closure",
    "finite_case_inputs": {
      "cases": [
        "stolen token no holder key",
        "parent key child token",
        "body task other",
        "holder other",
        "wrong endpoint query for invoke",
        "same proof replay",
        "other tenant/task/grant/holder/kid",
        "root/mid/leaf revoke",
        "actual current token expiry",
        "key disable"
      ],
      "management_routes": [
        "/sign",
        "/recover",
        "/settle"
      ],
      "aliases": [
        "notification.send",
        "request.read",
        "document.read",
        "order.create"
      ],
      "oracle": "all persisted families zero unauthorized extra effects; STAGED allowance separately counted",
      "deadlines": {
        "status": "PLANNED_NOT_RUN",
        "clock": "Actual signed AS claims/PG timestamptz and observed clock_timestamp(), never forged DTO or patched clock",
        "proof": "Genuinely signed lifetime1s proof: exp=actual signing iat+1. Barrier reached and observed before release; positive release only DBclock<exp; negative release only DBclock>=exp; exclusive expiry/future skew5 unchanged.",
        "actual_AS_fixture": "Reuse A22 signed_env_window: root task expires_at=actual now+8s; mid requested ttl<=6s; leaf requested ttl3s; each real exchange ttl=min(requested,parent.exp-actual_now-2)>0. Verify parent.iat<=child.iat<child.exp<=parent.exp and actual persisted deadline. Exhausted issuance margin fails fixture, never skip/past timestamps. Record parent_iat/exp, now/requested/actual ttl; same/cross-second original cases retained.",
        "target_deadlines": [
          "proof.exp",
          "query token.exp",
          "DB root.expires_at",
          "DB mid.expires_at",
          "DB leaf.expires_at"
        ],
        "groups": "Each newly added dependency release-before / release-at-or-after genuine deadline each10 rounds. Original8 wait groups and4 actual AS window groups remain separately required, not renamed/reduced. Parent expiry may also expire descendants; do not claim isolated parent expiry.",
        "timeout_seconds": {
          "observe_barrier": 5,
          "future_result": 5,
          "owned_child_start_stop": 10,
          "connect": 5
        },
        "SQL_timeout_ms": {
          "lock": 10000,
          "statement": 15000
        },
        "failure": "Unreachable barrier/positive window exhaustion is FAIL with raw evidence; no run-time skip, no sleep-only race"
      }
    },
    "case_values_status": "PROPOSED_FINITE_VALUES_NOT_ACTUAL_PARAMETERS_NOT_RUN"
  },
  {
    "node_binding_id": "N033",
    "kind": "planned_test",
    "planned_file": "tests/integration/test_gateway_receipt_https.py",
    "planned_function": "test_https_real_legal_256_sku_capacity_receipt_pipeline",
    "sole_initial_owner": "a23-https-r1-20261005",
    "phase": "https_fixture_demo",
    "status": "PLANNED_NOT_IMPLEMENTED_NOT_COLLECTED_NOT_RUN",
    "parameter_case_contract": {
      "case_labels": [
        "source_CA_SAN_legal_256SKU",
        "wheel_CA_SAN_legal_256SKU"
      ],
      "not_cartesian": true,
      "future_actual_parameters": "Bind implemented exact parameterized nodes after native stop; labels express local semantic cases, not invented argument names.",
      "allocation": "Case labels/explicit value sets are local finite obligations, not automatic cross products. Actual implemented collected nodeids/assertion lines/run evidence mandatory later."
    },
    "local_assertions": [
      {
        "id": "N033.A1",
        "text": "After core freeze, same legal256SKU actual AS root/two-child/public accept/PG terminal/publication/query/offline pipeline through separate true CA/SAN AS/GW processes; measure original component sizes."
      },
      {
        "id": "N033.A2",
        "text": "No fake DTO/synthetic wide256x128 claim; retain original component/JWS/global limits and public65536/503 proof rollback; preserve real failure evidence and conditional gate."
      }
    ],
    "actual_source_lines": null,
    "actual_collected_nodeids": [],
    "required_final_execution": "sole integrator and fresh reviewer separately source + noneditable wheel after all native stop/exclusive transfer; not initial owner proof of global closure",
    "finite_case_inputs": {
      "status": "NOT_CONFIRMED_NOT_RUN",
      "SKUs": [
        "s000",
        "s001",
        "s002",
        "s003",
        "s004",
        "s005",
        "s006",
        "s007",
        "s008",
        "s009",
        "s010",
        "s011",
        "s012",
        "s013",
        "s014",
        "s015",
        "s016",
        "s017",
        "s018",
        "s019",
        "s020",
        "s021",
        "s022",
        "s023",
        "s024",
        "s025",
        "s026",
        "s027",
        "s028",
        "s029",
        "s030",
        "s031",
        "s032",
        "s033",
        "s034",
        "s035",
        "s036",
        "s037",
        "s038",
        "s039",
        "s040",
        "s041",
        "s042",
        "s043",
        "s044",
        "s045",
        "s046",
        "s047",
        "s048",
        "s049",
        "s050",
        "s051",
        "s052",
        "s053",
        "s054",
        "s055",
        "s056",
        "s057",
        "s058",
        "s059",
        "s060",
        "s061",
        "s062",
        "s063",
        "s064",
        "s065",
        "s066",
        "s067",
        "s068",
        "s069",
        "s070",
        "s071",
        "s072",
        "s073",
        "s074",
        "s075",
        "s076",
        "s077",
        "s078",
        "s079",
        "s080",
        "s081",
        "s082",
        "s083",
        "s084",
        "s085",
        "s086",
        "s087",
        "s088",
        "s089",
        "s090",
        "s091",
        "s092",
        "s093",
        "s094",
        "s095",
        "s096",
        "s097",
        "s098",
        "s099",
        "s100",
        "s101",
        "s102",
        "s103",
        "s104",
        "s105",
        "s106",
        "s107",
        "s108",
        "s109",
        "s110",
        "s111",
        "s112",
        "s113",
        "s114",
        "s115",
        "s116",
        "s117",
        "s118",
        "s119",
        "s120",
        "s121",
        "s122",
        "s123",
        "s124",
        "s125",
        "s126",
        "s127",
        "s128",
        "s129",
        "s130",
        "s131",
        "s132",
        "s133",
        "s134",
        "s135",
        "s136",
        "s137",
        "s138",
        "s139",
        "s140",
        "s141",
        "s142",
        "s143",
        "s144",
        "s145",
        "s146",
        "s147",
        "s148",
        "s149",
        "s150",
        "s151",
        "s152",
        "s153",
        "s154",
        "s155",
        "s156",
        "s157",
        "s158",
        "s159",
        "s160",
        "s161",
        "s162",
        "s163",
        "s164",
        "s165",
        "s166",
        "s167",
        "s168",
        "s169",
        "s170",
        "s171",
        "s172",
        "s173",
        "s174",
        "s175",
        "s176",
        "s177",
        "s178",
        "s179",
        "s180",
        "s181",
        "s182",
        "s183",
        "s184",
        "s185",
        "s186",
        "s187",
        "s188",
        "s189",
        "s190",
        "s191",
        "s192",
        "s193",
        "s194",
        "s195",
        "s196",
        "s197",
        "s198",
        "s199",
        "s200",
        "s201",
        "s202",
        "s203",
        "s204",
        "s205",
        "s206",
        "s207",
        "s208",
        "s209",
        "s210",
        "s211",
        "s212",
        "s213",
        "s214",
        "s215",
        "s216",
        "s217",
        "s218",
        "s219",
        "s220",
        "s221",
        "s222",
        "s223",
        "s224",
        "s225",
        "s226",
        "s227",
        "s228",
        "s229",
        "s230",
        "s231",
        "s232",
        "s233",
        "s234",
        "s235",
        "s236",
        "s237",
        "s238",
        "s239",
        "s240",
        "s241",
        "s242",
        "s243",
        "s244",
        "s245",
        "s246",
        "s247",
        "s248",
        "s249",
        "s250",
        "s251",
        "s252",
        "s253",
        "s254",
        "s255"
      ],
      "quantity": 1,
      "unit_price_fen": 1,
      "total_fen": 256,
      "pipeline": "Actual AS login/consent root and two real exchanges allowing256 short unique SKU; actual public accept/PG quote/result/terminal/outbox/real publish/current query/offline in source+noneditablewheel. These are proposed fixture values, not observed reachable capacity. Core never consumes future HTTPS/CLI fixture; HTTPS later true CA/SAN repeats same path.",
      "measure": [
        "each AS/token/proof/receipt ASCII JWS<=16384",
        "PermissionSource material/request/result each original65536/depth64/nodes4096/stringbytes65536",
        "actual canonical request/quote/result/ledger/receipt and public envelope bytes"
      ],
      "gate": "Only actual legal AS256 full-path aggregate early rejection can trigger exact path29 evidence/receipt.py expansion by controller and NEW independent PACKAGE_REVIEW; retain original failures. DTO/blob arithmetic is not reachability.",
      "conditional_fix": "strict AG-EVIDENCE-1 exact outer fields, each component old canonical profile; ledger dedicated signed-delta codec; exact outer=2+sum(len(canonical key)+1+len(canonical value))+(field_count-1)<=1048576. Ancestors1..3/JWS16384/globalJSON/signature/all17/typ unchanged; public envelope65536 unchanged, oversize503 proof rollback."
    },
    "case_values_status": "PROPOSED_FINITE_VALUES_NOT_ACTUAL_PARAMETERS_NOT_RUN"
  },
  {
    "node_binding_id": "N035",
    "kind": "planned_test",
    "planned_file": "tests/integration/test_gateway_receipt_https.py",
    "planned_function": "test_a2_complete_receipt_closure",
    "sole_initial_owner": "a23-https-r1-20261005",
    "phase": "https_fixture_demo",
    "status": "PLANNED_NOT_IMPLEMENTED_NOT_COLLECTED_NOT_RUN",
    "parameter_case_contract": {
      "case_labels": [
        "final_real_receipt_closure"
      ],
      "not_cartesian": true,
      "future_actual_parameters": "Bind implemented exact parameterized nodes after native stop; labels express local semantic cases, not invented argument names.",
      "allocation": "Case labels/explicit value sets are local finite obligations, not automatic cross products. Actual implemented collected nodeids/assertion lines/run evidence mandatory later."
    },
    "local_assertions": [
      {
        "id": "N035.A1",
        "text": "Final real HTTPS joint scene reruns canonical4/version1 closure and own published/current query/offline outcomes."
      },
      {
        "id": "N035.A2",
        "text": "Function is not proxy for all119/112, P01-P21 or30 goals; exact whole matrix and A3 boundaries bind separate integrator documentary/full-suite evidence."
      }
    ],
    "actual_source_lines": null,
    "actual_collected_nodeids": [],
    "required_final_execution": "sole integrator and fresh reviewer separately source + noneditable wheel after all native stop/exclusive transfer; not initial owner proof of global closure",
    "finite_case_inputs": {
      "scene": {
        "hosts": [
          "auth.agent-guard.test",
          "gateway.agent-guard.test"
        ],
        "tool_version": "1",
        "tools": [
          "procurement.request.read",
          "procurement.document.read",
          "procurement.order.create",
          "notification.template.send"
        ],
        "params": [
          {
            "request_id": "req-001"
          },
          {
            "request_id": "req-001",
            "document_id": "doc-001"
          },
          {
            "request_id": "req-001",
            "quote_id": "quote-001",
            "quote_version": "1",
            "items": [
              {
                "sku": "sku-001",
                "quantity": 1
              }
            ],
            "delivery_id": "office-001"
          },
          {
            "template_id": "order-created",
            "recipient_id": "user-demo-001",
            "operation_id": "actual accessible persistent prior operation ID"
          }
        ],
        "OIDC": "Actual network cookie jar: GET login CSRF→POST password→authorize exact registered redirect/state/nonce/S256 SHA256 verifier→consent/code→actual AGPoP code exchange→RP independent IDToken signature/iss/aud/exp/auth_time/nonce verify. Preserve actual Secure/HttpOnly/SameSite cookie policies. Two real AS exchanges use distinct Basic clients/SM2 keys root→child→child.",
        "closure": "One CA/SAN AS+GW multi-process scene, independent downstream persistent terminal, actual InternalPublisher/current fresh-proof query/independent operation-scoped ReceiptTrust offline; no historical TLS stitching",
        "aliases_negative_only": [
          "notification.send",
          "request.read",
          "document.read",
          "order.create"
        ]
      },
      "local_scope": "own real receipt joint closure; whole119/112 G1/G2 separate"
    },
    "case_values_status": "PROPOSED_FINITE_VALUES_NOT_ACTUAL_PARAMETERS_NOT_RUN"
  }
]

```



完整局部 source+非editablewheel实跑、质量/受影响旧回归/真PID与TLS/全部ag及DS oracle，自有实际 command/exit/pass-fail-error-skip/完整日志/JUnit/SHA；保留首次失败/补正原件。

交完整 implementation.md、API/源SHA、local binding、command/raw manifests、开始结束readonly Git/scope/子PID/资源清理核验。所有 wrapper 真退出、无owned资源余留后原生 STOP，READY_FOR_INTEGRATION；不是 ACCEPTED。不修改共享core、正式包、SQL/锁/依赖/CI；范围必要变化先 NEEDS_REPLAN 停写。

全部STOP后sole integrator联合新CLI+HTTPS、完整119/112及所有历史/P01–21/30goal边界sourcewheel，再fresh完整独立验收。最新真人要求完整A2验收和A3规划完成后停止，本次A3只规划、不实施。

HTTPS专项：只直接冻结InternalPublisher，不导入尚未停止CLI。真实固定AS/GWhostname受信CA/SAN+独立PID/cookie login/CSRF/consent/code/S256/IDToken+两次真实exchange+四canonical ToolId/version字符串1+独立下游terminal+真实publish/query/independentofflineSDK。wrongCA/hostname、盗token/parentkey/body/holder/endpoint/replay/crossowner/revoke/TTL及managementroutes拒例全部beforeafter原子效果/隐私。真实256SKU sourcewheel同链各组件原限额保留。tools/a2_receipt_demo.py无需模型API、不得test-only假验权或prodskip。
