use agent_guard_threshold_demo::{
    DemoActionGate, DemoError, OrderAction, OrderItem, sign_action, trusted_dealer_setup,
};
use frost_ed25519 as frost;
use std::collections::BTreeMap;

fn action() -> OrderAction {
    let mut action = OrderAction {
        version: 1,
        tenant_id: "tenant-demo".into(),
        task_id: "task-001".into(),
        root_grant_id: "grant-root".into(),
        grant_id: "grant-leaf".into(),
        holder_client_id: "agent-executor".into(),
        holder_kid: "kid-exec".into(),
        audience: "gateway-demo".into(),
        tool_id: "procurement.order.create".into(),
        currency: "CNY".into(),
        policy_version: 1,
        key_epoch: 1,
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
        expires_at: 2_000,
    };
    action.canonical_params_sha256 = action.compute_params_digest().unwrap();
    action
}

#[test]
fn each_pair_can_sign_and_group_key_verifies() {
    for pair in [(0, 1), (0, 2), (1, 2)] {
        let (signers, public) = trusted_dealer_setup().unwrap();
        let act = action();
        let signature = sign_action(
            &act,
            1_000,
            vec![signers[pair.0].commit(), signers[pair.1].commit()],
            &public,
        )
        .unwrap();
        public.verify(&act, &signature).unwrap();
    }
}

#[test]
fn one_of_three_and_duplicate_identity_cannot_sign() {
    let (signers, public) = trusted_dealer_setup().unwrap();
    assert!(matches!(
        sign_action(&action(), 1_000, vec![signers[0].commit()], &public),
        Err(DemoError::TooFewSigners)
    ));
    assert!(matches!(
        sign_action(
            &action(),
            1_000,
            vec![signers[0].commit(), signers[0].commit()],
            &public
        ),
        Err(DemoError::DuplicateSigner)
    ));
}

#[test]
fn signed_action_cannot_be_changed_or_replayed() {
    let (signers, public) = trusted_dealer_setup().unwrap();
    let act = action();
    let signature = sign_action(
        &act,
        1_000,
        vec![signers[0].commit(), signers[2].commit()],
        &public,
    )
    .unwrap();
    let mut changed = act.clone();
    changed.amount_fen += 1;
    assert_eq!(
        public.verify(&changed, &signature),
        Err(DemoError::InvalidSignature)
    );
    changed = act.clone();
    changed.delivery_id = "other-office".into();
    assert_eq!(
        public.verify(&changed, &signature),
        Err(DemoError::InvalidAction)
    );
    changed.canonical_params_sha256 = changed.compute_params_digest().unwrap();
    assert_eq!(
        public.verify(&changed, &signature),
        Err(DemoError::InvalidSignature)
    );
    changed = act.clone();
    changed.action_id = "order-002".into();
    assert_eq!(
        public.verify(&changed, &signature),
        Err(DemoError::InvalidSignature)
    );
    changed = act.clone();
    changed.holder_kid = "other-key".into();
    assert_eq!(
        public.verify(&changed, &signature),
        Err(DemoError::InvalidSignature)
    );
    changed = act.clone();
    changed.policy_version += 1;
    assert_eq!(
        public.verify(&changed, &signature),
        Err(DemoError::InvalidSignature)
    );
    changed = act.clone();
    changed.key_epoch += 1;
    assert_eq!(
        public.verify(&changed, &signature),
        Err(DemoError::InvalidSignature)
    );
    changed = act.clone();
    changed.root_grant_id = "other-root".into();
    assert_eq!(
        public.verify(&changed, &signature),
        Err(DemoError::InvalidSignature)
    );
    let mut same_business_key = act.clone();
    same_business_key.action_id = "order-002".into();
    let second_signature = sign_action(
        &same_business_key,
        1_000,
        vec![signers[1].commit(), signers[2].commit()],
        &public,
    )
    .unwrap();
    let mut gate = DemoActionGate::new(public);
    gate.accept(&act, &signature, 1_000).unwrap();
    assert_eq!(
        gate.accept(&act, &signature, 1_000),
        Err(DemoError::AlreadyAccepted)
    );
    assert_eq!(
        gate.accept(&same_business_key, &second_signature, 1_000),
        Err(DemoError::AlreadyAccepted)
    );
}

#[test]
fn expiry_and_invalid_schema_fail_closed() {
    let (signers, public) = trusted_dealer_setup().unwrap();
    let act = action();
    assert!(matches!(
        sign_action(
            &act,
            2_000,
            vec![signers[0].commit(), signers[1].commit()],
            &public
        ),
        Err(DemoError::Expired)
    ));
    let raw = serde_json::to_string(&act).unwrap();
    let extra = raw.replace("\"version\":1", "\"version\":1,\"new_security_field\":true");
    assert!(serde_json::from_str::<OrderAction>(&extra).is_err());
    let mut invalid = act;
    invalid.items[0].quantity = 0;
    assert_eq!(invalid.message(), Err(DemoError::InvalidAction));
}

#[test]
fn signer_refuses_a_signing_package_for_another_action() {
    let (signers, _) = trusted_dealer_setup().unwrap();
    let pending = signers[0].commit();
    let mut commitments = BTreeMap::new();
    commitments.insert(pending.id(), pending.commitments());
    let original = action();
    let mut other = original.clone();
    other.action_id = "order-002".into();
    let wrong_package = frost::SigningPackage::new(commitments, &other.message().unwrap());
    assert!(matches!(
        pending.sign(&original, 1_000, &wrong_package),
        Err(DemoError::WrongAction)
    ));
}

#[test]
fn valid_signature_expires_before_acceptance() {
    let (signers, public) = trusted_dealer_setup().unwrap();
    let act = action();
    let signature = sign_action(
        &act,
        1_000,
        vec![signers[0].commit(), signers[1].commit()],
        &public,
    )
    .unwrap();
    let mut gate = DemoActionGate::new(public);
    assert_eq!(
        gate.accept(&act, &signature, 2_000),
        Err(DemoError::Expired)
    );
}
