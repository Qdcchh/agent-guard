//! V2 approval-action tests: exact bytes, quorum, binding and tamper rejection.
//!
//! V1 is deliberately frozen: the committed public vector must still verify
//! with the untouched V1 encoder.

use agent_guard_threshold_demo::{
    ACTION_DOMAIN_V1, ACTION_DOMAIN_V2, AnyAction, ApprovalActionV2, DemoError, OrderAction,
    OrderItem, sign_action_v2, trusted_dealer_setup,
};
use frost_ed25519 as frost;
use sha2::{Digest, Sha256};

fn v2_action() -> ApprovalActionV2 {
    let mut action = ApprovalActionV2 {
        version: 2,
        tenant_id: "tenant-demo".into(),
        task_id: "task-001".into(),
        root_grant_id: "grant-root".into(),
        grant_id: "grant-leaf".into(),
        path_grant_ids: vec!["grant-root".into(), "grant-mid".into(), "grant-leaf".into()],
        holder_client_id: "agent-executor".into(),
        holder_kid: "kid-exec".into(),
        audience: "https://gateway.agent-guard.test".into(),
        tool_id: "procurement.order.create".into(),
        tool_version: "1".into(),
        currency: "CNY".into(),
        policy_version: 7,
        key_epoch: 3,
        action_id: "order-001".into(),
        idempotency_key: "idem-001".into(),
        request_id: "req-001".into(),
        quote_id: "quote-001".into(),
        quote_version: "1".into(),
        items: vec![OrderItem {
            sku: "sku-001".into(),
            quantity: 1,
        }],
        delivery_id: "office-001".into(),
        amount_fen: 70_000,
        canonical_params_sha256: String::new(),
        expires_at: 4_102_444_800,
    };
    action.canonical_params_sha256 = action.compute_params_digest().unwrap();
    action
}

#[test]
fn v1_public_vector_bytes_stay_frozen() {
    let raw = std::fs::read_to_string(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/tests/public-vector.json"
    ))
    .unwrap();
    let vector: serde_json::Value = serde_json::from_str(&raw).unwrap();
    let action: OrderAction = serde_json::from_value(vector["action"].clone()).unwrap();
    let message = action.message().unwrap();
    assert!(message.starts_with(ACTION_DOMAIN_V1));
    assert!(!message.starts_with(ACTION_DOMAIN_V2));
    assert_eq!(
        hex::encode(Sha256::digest(&message)),
        vector["message_sha256"].as_str().unwrap()
    );
    let key_bytes = hex::decode(vector["group_public_key_hex"].as_str().unwrap()).unwrap();
    let key = frost::VerifyingKey::deserialize(&key_bytes).unwrap();
    let signature_bytes = hex::decode(vector["signature_hex"].as_str().unwrap()).unwrap();
    let signature = frost::Signature::deserialize(&signature_bytes).unwrap();
    key.verify(&message, &signature).unwrap();
}

#[test]
fn v2_pair_signing_round_trip_and_wrong_key_rejection() {
    for pair in [(0, 1), (0, 2), (1, 2)] {
        let (signers, public) = trusted_dealer_setup().unwrap();
        let action = v2_action();
        let signature = sign_action_v2(
            &action,
            1_000,
            vec![signers[pair.0].commit(), signers[pair.1].commit()],
            &public,
        )
        .unwrap();
        public.verify_v2(&action, &signature).unwrap();
        let message = action.message().unwrap();
        assert!(message.starts_with(ACTION_DOMAIN_V2));

        let (_, other_public) = trusted_dealer_setup().unwrap();
        assert_eq!(
            other_public.verify_v2(&action, &signature),
            Err(DemoError::InvalidSignature)
        );
    }
}

#[test]
fn v2_one_of_three_and_duplicate_identity_cannot_sign() {
    let (signers, public) = trusted_dealer_setup().unwrap();
    let action = v2_action();
    assert!(matches!(
        sign_action_v2(&action, 1_000, vec![signers[0].commit()], &public),
        Err(DemoError::TooFewSigners)
    ));
    assert!(matches!(
        sign_action_v2(
            &action,
            1_000,
            vec![signers[0].commit(), signers[0].commit()],
            &public
        ),
        Err(DemoError::DuplicateSigner)
    ));
}

#[test]
fn v2_tampered_fields_never_verify() {
    let (signers, public) = trusted_dealer_setup().unwrap();
    let action = v2_action();
    let signature = sign_action_v2(
        &action,
        1_000,
        vec![signers[0].commit(), signers[2].commit()],
        &public,
    )
    .unwrap();
    let mutations: Vec<(&str, Box<dyn Fn(&mut ApprovalActionV2)>)> = vec![
        (
            "amount",
            Box::new(|a: &mut ApprovalActionV2| a.amount_fen += 1),
        ),
        (
            "delivery",
            Box::new(|a: &mut ApprovalActionV2| a.delivery_id = "other-office".into()),
        ),
        (
            "task",
            Box::new(|a: &mut ApprovalActionV2| a.task_id = "task-002".into()),
        ),
        (
            "holder_kid",
            Box::new(|a: &mut ApprovalActionV2| a.holder_kid = "kid-other".into()),
        ),
        (
            "tool_version",
            Box::new(|a: &mut ApprovalActionV2| a.tool_version = "2".into()),
        ),
        (
            "policy_version",
            Box::new(|a: &mut ApprovalActionV2| a.policy_version += 1),
        ),
        (
            "key_epoch",
            Box::new(|a: &mut ApprovalActionV2| a.key_epoch += 1),
        ),
        (
            "action_id",
            Box::new(|a: &mut ApprovalActionV2| a.action_id = "order-002".into()),
        ),
        (
            "path",
            Box::new(|a: &mut ApprovalActionV2| a.path_grant_ids[1] = "grant-mid-other".into()),
        ),
        (
            "root",
            Box::new(|a: &mut ApprovalActionV2| a.root_grant_id = "grant-root-other".into()),
        ),
        (
            "expiry",
            Box::new(|a: &mut ApprovalActionV2| a.expires_at += 1),
        ),
    ];
    for (name, mutate) in mutations {
        let mut changed = action.clone();
        mutate(&mut changed);
        let outcome = match changed.message() {
            Ok(_) => public.verify_v2(&changed, &signature),
            Err(error) => Err(error),
        };
        assert!(
            matches!(
                outcome,
                Err(DemoError::InvalidSignature) | Err(DemoError::InvalidAction)
            ),
            "mutation {name} unexpectedly verified"
        );
    }
}

#[test]
fn v2_expiry_before_signing_and_invalid_schema_fail_closed() {
    let (signers, public) = trusted_dealer_setup().unwrap();
    let action = v2_action();
    assert!(matches!(
        sign_action_v2(
            &action,
            4_102_444_800,
            vec![signers[0].commit(), signers[1].commit()],
            &public
        ),
        Err(DemoError::Expired)
    ));

    let mut invalid = action.clone();
    invalid.items[0].quantity = 0;
    assert_eq!(invalid.message(), Err(DemoError::InvalidAction));

    let mut missing_path = action.clone();
    missing_path.path_grant_ids = vec!["grant-root".into()];
    assert_eq!(missing_path.message(), Err(DemoError::InvalidAction));

    let mut duplicate_path = action.clone();
    duplicate_path.path_grant_ids = vec![
        "grant-root".into(),
        "grant-root".into(),
        "grant-leaf".into(),
    ];
    assert_eq!(duplicate_path.message(), Err(DemoError::InvalidAction));

    let mut forged_leaf = action.clone();
    forged_leaf.path_grant_ids[2] = "grant-other".into();
    assert_eq!(forged_leaf.message(), Err(DemoError::InvalidAction));

    let mut short_version = action.clone();
    short_version.tool_version = String::new();
    assert_eq!(short_version.message(), Err(DemoError::InvalidAction));
}

#[test]
fn action_deserialization_rejects_unknown_and_future_versions() {
    let raw = serde_json::to_string(&v2_action()).unwrap();
    let extra = raw.replace("\"version\":2", "\"version\":2,\"new_security_field\":true");
    assert!(serde_json::from_str::<AnyAction>(&extra).is_err());

    let future = raw.replace("\"version\":2", "\"version\":3");
    assert!(serde_json::from_str::<AnyAction>(&future).is_err());

    let v1_raw = std::fs::read_to_string(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/tests/public-vector.json"
    ))
    .unwrap();
    let vector: serde_json::Value = serde_json::from_str(&v1_raw).unwrap();
    let parsed: AnyAction = serde_json::from_value(vector["action"].clone()).unwrap();
    assert!(matches!(parsed, AnyAction::V1(_)));
    assert_eq!(parsed.tool_version(), "1");
    assert_eq!(
        parsed.path_grant_ids(),
        vec!["grant-root".to_string(), "grant-leaf".to_string()]
    );
}

#[test]
fn v1_message_is_unchanged_by_v2_support() {
    let raw = std::fs::read_to_string(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/tests/public-vector.json"
    ))
    .unwrap();
    let vector: serde_json::Value = serde_json::from_str(&raw).unwrap();
    let action: OrderAction = serde_json::from_value(vector["action"].clone()).unwrap();
    let encoded = serde_json::to_vec(&action).unwrap();
    assert!(encoded.starts_with(br#"{"version":1,"#));
    assert!(!encoded.windows(10).any(|w| w == b"tool_versi"));
    let mut message = ACTION_DOMAIN_V1.to_vec();
    message.extend(encoded);
    assert_eq!(message, action.message().unwrap());
}
