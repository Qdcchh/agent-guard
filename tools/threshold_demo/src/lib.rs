//! Standalone teaching prototype. No gateway integration or production key storage.

use frost_ed25519 as frost;
use rand::rngs::OsRng;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, HashSet};

/// Domain separation for the original prototype action. Frozen: never change.
pub const ACTION_DOMAIN_V1: &[u8] = b"AGENT-GUARD-THRESHOLD-ACTION-V1\n";
/// Domain separation for the gateway approval action (adds tool version and the
/// complete root-to-leaf authorization path). Versioned separately so the V1
/// byte encoding stays exactly as delivered.
pub const ACTION_DOMAIN_V2: &[u8] = b"AGENT-GUARD-THRESHOLD-ACTION-V2\n";
/// Domain separation for the x402-bound approval action. It appends the exact
/// payment-intent digest to the V2 action; the V2 bytes and domain stay frozen.
pub const ACTION_DOMAIN_V3: &[u8] = b"AGENT-GUARD-THRESHOLD-ACTION-V3\n";

/// Maximum item count accepted by either action version.
pub const MAX_ACTION_ITEMS: usize = 256;
/// Maximum root-to-leaf path length of the execution ledger.
pub const MAX_ACTION_PATH: usize = 3;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct OrderItem {
    pub sku: String,
    pub quantity: u16,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct OrderAction {
    pub version: u8,
    pub tenant_id: String,
    pub task_id: String,
    pub root_grant_id: String,
    pub grant_id: String,
    pub holder_client_id: String,
    pub holder_kid: String,
    pub audience: String,
    pub tool_id: String,
    pub currency: String,
    pub policy_version: u32,
    pub key_epoch: u32,
    pub action_id: String,
    pub idempotency_key: String,
    pub request_id: String,
    pub quote_id: String,
    pub quote_version: String,
    pub items: Vec<OrderItem>,
    pub delivery_id: String,
    pub amount_fen: u64,
    pub canonical_params_sha256: String,
    pub expires_at: u64,
}

#[derive(Serialize)]
struct OrderParameters<'a> {
    request_id: &'a str,
    quote_id: &'a str,
    quote_version: &'a str,
    items: &'a [OrderItem],
    delivery_id: &'a str,
}

impl OrderAction {
    /// Digest of the full fixed order parameter structure in this prototype.
    pub fn compute_params_digest(&self) -> Result<String, DemoError> {
        let params = OrderParameters {
            request_id: &self.request_id,
            quote_id: &self.quote_id,
            quote_version: &self.quote_version,
            items: &self.items,
            delivery_id: &self.delivery_id,
        };
        let bytes = serde_json::to_vec(&params).map_err(|_| DemoError::InvalidAction)?;
        Ok(hex::encode(Sha256::digest(bytes)))
    }

    pub fn message(&self) -> Result<Vec<u8>, DemoError> {
        self.validate()?;
        let mut message = ACTION_DOMAIN_V1.to_vec();
        message.extend(serde_json::to_vec(self).map_err(|_| DemoError::InvalidAction)?);
        Ok(message)
    }

    fn validate(&self) -> Result<(), DemoError> {
        if self.version != 1
            || self.tool_id != "procurement.order.create"
            || self.currency != "CNY"
            || self.policy_version == 0
            || self.key_epoch == 0
            || self.items.is_empty()
            || self.items.len() > 256
            || self.items.iter().any(|item| {
                item.quantity == 0
                    || item.sku.is_empty()
                    || item.sku.len() > 128
                    || !item
                        .sku
                        .bytes()
                        .all(|byte| byte.is_ascii_alphanumeric() || b"._:-@".contains(&byte))
            })
            || self
                .items
                .iter()
                .map(|item| &item.sku)
                .collect::<HashSet<_>>()
                .len()
                != self.items.len()
            || self.amount_fen > 9_007_199_254_740_991
            || self.expires_at == 0
            || self.canonical_params_sha256 != self.compute_params_digest()?
            || [
                &self.tenant_id,
                &self.task_id,
                &self.root_grant_id,
                &self.grant_id,
                &self.holder_client_id,
                &self.holder_kid,
                &self.audience,
                &self.action_id,
                &self.idempotency_key,
                &self.request_id,
                &self.quote_id,
                &self.quote_version,
                &self.delivery_id,
            ]
            .iter()
            .any(|value| {
                value.is_empty()
                    || value.len() > 128
                    || !value
                        .bytes()
                        .all(|byte| byte.is_ascii_alphanumeric() || b"._:-@".contains(&byte))
            })
        {
            return Err(DemoError::InvalidAction);
        }
        Ok(())
    }
}

/// Versioned approval action bound by the gateway `ag-approval` header.
///
/// Version 2 of the prototype action. It adds the exact tool version and the
/// complete root-to-leaf authorization path, which version 1 did not carry.
/// The message is `AGENT-GUARD-THRESHOLD-ACTION-V2\n` followed by the
/// deterministic JSON encoding of the fixed struct below (field order is the
/// wire order). That encoding is local to this prototype and is not the
/// repository's GM-MVP-1/JWS encoding.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ApprovalActionV2 {
    pub version: u8,
    pub tenant_id: String,
    pub task_id: String,
    pub root_grant_id: String,
    pub grant_id: String,
    pub path_grant_ids: Vec<String>,
    pub holder_client_id: String,
    pub holder_kid: String,
    pub audience: String,
    pub tool_id: String,
    pub tool_version: String,
    pub currency: String,
    pub policy_version: u32,
    pub key_epoch: u32,
    pub action_id: String,
    pub idempotency_key: String,
    pub request_id: String,
    pub quote_id: String,
    pub quote_version: String,
    pub items: Vec<OrderItem>,
    pub delivery_id: String,
    pub amount_fen: u64,
    pub canonical_params_sha256: String,
    pub expires_at: u64,
}

impl ApprovalActionV2 {
    /// Digest of the full fixed order parameter structure in this prototype.
    pub fn compute_params_digest(&self) -> Result<String, DemoError> {
        let params = OrderParameters {
            request_id: &self.request_id,
            quote_id: &self.quote_id,
            quote_version: &self.quote_version,
            items: &self.items,
            delivery_id: &self.delivery_id,
        };
        let bytes = serde_json::to_vec(&params).map_err(|_| DemoError::InvalidAction)?;
        Ok(hex::encode(Sha256::digest(bytes)))
    }

    pub fn message(&self) -> Result<Vec<u8>, DemoError> {
        self.validate()?;
        let mut message = ACTION_DOMAIN_V2.to_vec();
        message.extend(serde_json::to_vec(self).map_err(|_| DemoError::InvalidAction)?);
        Ok(message)
    }

    fn validate(&self) -> Result<(), DemoError> {
        if self.version != 2
            || self.tool_id != "procurement.order.create"
            || self.tool_version != "1"
            || self.currency != "CNY"
            || self.policy_version == 0
            || self.key_epoch == 0
            || self.items.is_empty()
            || self.items.len() > MAX_ACTION_ITEMS
            || self.path_grant_ids.is_empty()
            || self.path_grant_ids.len() > MAX_ACTION_PATH
            || self.path_grant_ids[0] != self.root_grant_id
            || self.path_grant_ids[self.path_grant_ids.len() - 1] != self.grant_id
            || self.path_grant_ids.iter().collect::<HashSet<_>>().len() != self.path_grant_ids.len()
            || self.items.iter().any(|item| {
                item.quantity == 0
                    || item.sku.is_empty()
                    || item.sku.len() > 128
                    || !item
                        .sku
                        .bytes()
                        .all(|byte| byte.is_ascii_alphanumeric() || b"._:-@".contains(&byte))
            })
            || self
                .items
                .iter()
                .map(|item| &item.sku)
                .collect::<HashSet<_>>()
                .len()
                != self.items.len()
            || self.amount_fen > 9_007_199_254_740_991
            || self.expires_at == 0
            || self.canonical_params_sha256 != self.compute_params_digest()?
            || self.holder_kid.is_empty()
            || self.holder_kid.len() > 256
            || !self
                .holder_kid
                .bytes()
                .all(|byte| (0x21..0x7f).contains(&byte))
            || [
                &self.tenant_id,
                &self.task_id,
                &self.root_grant_id,
                &self.grant_id,
                &self.holder_client_id,
                &self.action_id,
                &self.idempotency_key,
                &self.request_id,
                &self.quote_id,
                &self.quote_version,
                &self.delivery_id,
            ]
            .iter()
            .any(|value| {
                value.is_empty()
                    || value.len() > 128
                    || !value
                        .bytes()
                        .all(|byte| byte.is_ascii_alphanumeric() || b"._:-@".contains(&byte))
            })
            || self.path_grant_ids.iter().any(|value| {
                value.is_empty()
                    || value.len() > 128
                    || !value
                        .bytes()
                        .all(|byte| byte.is_ascii_alphanumeric() || b"._:-@".contains(&byte))
            })
            || self.audience.is_empty()
            || self.audience.len() > 128
            || !self
                .audience
                .bytes()
                .all(|byte| (0x21..0x7f).contains(&byte))
        {
            return Err(DemoError::InvalidAction);
        }
        Ok(())
    }
}

/// Version 3 of the gateway approval: exactly the V2 action plus the x402
/// payment-intent digest as the last field. The digest is covered by the group
/// signature, so a quorum approves the concrete payment facts, not only the
/// procurement order. All other V2 checks are reused unchanged.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ApprovalActionV3 {
    pub version: u8,
    pub tenant_id: String,
    pub task_id: String,
    pub root_grant_id: String,
    pub grant_id: String,
    pub path_grant_ids: Vec<String>,
    pub holder_client_id: String,
    pub holder_kid: String,
    pub audience: String,
    pub tool_id: String,
    pub tool_version: String,
    pub currency: String,
    pub policy_version: u32,
    pub key_epoch: u32,
    pub action_id: String,
    pub idempotency_key: String,
    pub request_id: String,
    pub quote_id: String,
    pub quote_version: String,
    pub items: Vec<OrderItem>,
    pub delivery_id: String,
    pub amount_fen: u64,
    pub canonical_params_sha256: String,
    pub expires_at: u64,
    pub payment_digest: String,
}

impl ApprovalActionV3 {
    pub fn compute_params_digest(&self) -> Result<String, DemoError> {
        let params = OrderParameters {
            request_id: &self.request_id,
            quote_id: &self.quote_id,
            quote_version: &self.quote_version,
            items: &self.items,
            delivery_id: &self.delivery_id,
        };
        let bytes = serde_json::to_vec(&params).map_err(|_| DemoError::InvalidAction)?;
        Ok(hex::encode(Sha256::digest(bytes)))
    }

    pub fn message(&self) -> Result<Vec<u8>, DemoError> {
        self.validate()?;
        let mut message = ACTION_DOMAIN_V3.to_vec();
        message.extend(serde_json::to_vec(self).map_err(|_| DemoError::InvalidAction)?);
        Ok(message)
    }

    fn validate(&self) -> Result<(), DemoError> {
        if self.version != 3
            || self.payment_digest.len() != 64
            || !self
                .payment_digest
                .bytes()
                .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
        {
            return Err(DemoError::InvalidAction);
        }
        // Reuse the frozen V2 validation over an identical V2-shaped copy.
        let base = ApprovalActionV2 {
            version: 2,
            tenant_id: self.tenant_id.clone(),
            task_id: self.task_id.clone(),
            root_grant_id: self.root_grant_id.clone(),
            grant_id: self.grant_id.clone(),
            path_grant_ids: self.path_grant_ids.clone(),
            holder_client_id: self.holder_client_id.clone(),
            holder_kid: self.holder_kid.clone(),
            audience: self.audience.clone(),
            tool_id: self.tool_id.clone(),
            tool_version: self.tool_version.clone(),
            currency: self.currency.clone(),
            policy_version: self.policy_version,
            key_epoch: self.key_epoch,
            action_id: self.action_id.clone(),
            idempotency_key: self.idempotency_key.clone(),
            request_id: self.request_id.clone(),
            quote_id: self.quote_id.clone(),
            quote_version: self.quote_version.clone(),
            items: self.items.clone(),
            delivery_id: self.delivery_id.clone(),
            amount_fen: self.amount_fen,
            canonical_params_sha256: self.canonical_params_sha256.clone(),
            expires_at: self.expires_at,
        };
        base.validate()
    }
}

/// Minimal versioned wrapper used by the CLI so one command can process either
/// action version without silently changing V1 bytes.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(untagged)]
pub enum AnyAction {
    V1(OrderAction),
    V2(ApprovalActionV2),
    V3(ApprovalActionV3),
}

impl<'de> Deserialize<'de> for AnyAction {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: serde::Deserializer<'de>,
    {
        let value = serde_json::Value::deserialize(deserializer)?;
        let version = value.get("version").and_then(|entry| entry.as_u64());
        match version {
            Some(1) => OrderAction::deserialize(value)
                .map(AnyAction::V1)
                .map_err(serde::de::Error::custom),
            Some(2) => ApprovalActionV2::deserialize(value)
                .map(AnyAction::V2)
                .map_err(serde::de::Error::custom),
            Some(3) => ApprovalActionV3::deserialize(value)
                .map(AnyAction::V3)
                .map_err(serde::de::Error::custom),
            _ => Err(serde::de::Error::custom(
                "unsupported threshold action version",
            )),
        }
    }
}

impl AnyAction {
    pub fn message(&self) -> Result<Vec<u8>, DemoError> {
        match self {
            AnyAction::V1(action) => action.message(),
            AnyAction::V2(action) => action.message(),
            AnyAction::V3(action) => action.message(),
        }
    }

    pub fn expires_at(&self) -> u64 {
        match self {
            AnyAction::V1(action) => action.expires_at,
            AnyAction::V2(action) => action.expires_at,
            AnyAction::V3(action) => action.expires_at,
        }
    }

    pub fn tenant_id(&self) -> &str {
        match self {
            AnyAction::V1(action) => &action.tenant_id,
            AnyAction::V2(action) => &action.tenant_id,
            AnyAction::V3(action) => &action.tenant_id,
        }
    }

    pub fn task_id(&self) -> &str {
        match self {
            AnyAction::V1(action) => &action.task_id,
            AnyAction::V2(action) => &action.task_id,
            AnyAction::V3(action) => &action.task_id,
        }
    }

    pub fn root_grant_id(&self) -> &str {
        match self {
            AnyAction::V1(action) => &action.root_grant_id,
            AnyAction::V2(action) => &action.root_grant_id,
            AnyAction::V3(action) => &action.root_grant_id,
        }
    }

    pub fn grant_id(&self) -> &str {
        match self {
            AnyAction::V1(action) => &action.grant_id,
            AnyAction::V2(action) => &action.grant_id,
            AnyAction::V3(action) => &action.grant_id,
        }
    }

    pub fn path_grant_ids(&self) -> Vec<String> {
        match self {
            AnyAction::V1(action) => vec![action.root_grant_id.clone(), action.grant_id.clone()],
            AnyAction::V2(action) => action.path_grant_ids.clone(),
            AnyAction::V3(action) => action.path_grant_ids.clone(),
        }
    }

    pub fn holder_client_id(&self) -> &str {
        match self {
            AnyAction::V1(action) => &action.holder_client_id,
            AnyAction::V2(action) => &action.holder_client_id,
            AnyAction::V3(action) => &action.holder_client_id,
        }
    }

    pub fn holder_kid(&self) -> &str {
        match self {
            AnyAction::V1(action) => &action.holder_kid,
            AnyAction::V2(action) => &action.holder_kid,
            AnyAction::V3(action) => &action.holder_kid,
        }
    }

    pub fn audience(&self) -> &str {
        match self {
            AnyAction::V1(action) => &action.audience,
            AnyAction::V2(action) => &action.audience,
            AnyAction::V3(action) => &action.audience,
        }
    }

    pub fn tool_id(&self) -> &str {
        match self {
            AnyAction::V1(action) => &action.tool_id,
            AnyAction::V2(action) => &action.tool_id,
            AnyAction::V3(action) => &action.tool_id,
        }
    }

    pub fn tool_version(&self) -> &str {
        match self {
            AnyAction::V1(_) => "1",
            AnyAction::V2(action) => &action.tool_version,
            AnyAction::V3(action) => &action.tool_version,
        }
    }

    pub fn policy_version(&self) -> u32 {
        match self {
            AnyAction::V1(action) => action.policy_version,
            AnyAction::V2(action) => action.policy_version,
            AnyAction::V3(action) => action.policy_version,
        }
    }

    pub fn key_epoch(&self) -> u32 {
        match self {
            AnyAction::V1(action) => action.key_epoch,
            AnyAction::V2(action) => action.key_epoch,
            AnyAction::V3(action) => action.key_epoch,
        }
    }

    pub fn currency(&self) -> &str {
        match self {
            AnyAction::V1(action) => &action.currency,
            AnyAction::V2(action) => &action.currency,
            AnyAction::V3(action) => &action.currency,
        }
    }

    pub fn amount_fen(&self) -> u64 {
        match self {
            AnyAction::V1(action) => action.amount_fen,
            AnyAction::V2(action) => action.amount_fen,
            AnyAction::V3(action) => action.amount_fen,
        }
    }

    pub fn action_id(&self) -> &str {
        match self {
            AnyAction::V1(action) => &action.action_id,
            AnyAction::V2(action) => &action.action_id,
            AnyAction::V3(action) => &action.action_id,
        }
    }

    pub fn idempotency_key(&self) -> &str {
        match self {
            AnyAction::V1(action) => &action.idempotency_key,
            AnyAction::V2(action) => &action.idempotency_key,
            AnyAction::V3(action) => &action.idempotency_key,
        }
    }

    pub fn canonical_params_sha256(&self) -> &str {
        match self {
            AnyAction::V1(action) => &action.canonical_params_sha256,
            AnyAction::V2(action) => &action.canonical_params_sha256,
            AnyAction::V3(action) => &action.canonical_params_sha256,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DemoError {
    InvalidAction,
    Expired,
    TooFewSigners,
    DuplicateSigner,
    WrongAction,
    InvalidSignature,
    AlreadyAccepted,
    Frost,
}

impl std::fmt::Display for DemoError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(formatter, "{self:?}")
    }
}

impl std::error::Error for DemoError {}

impl From<frost::Error> for DemoError {
    fn from(_: frost::Error) -> Self {
        Self::Frost
    }
}

/// One owner of one dealer-generated key share. The full secret is never reconstructed.
pub struct Signer {
    id: frost::Identifier,
    key: frost::keys::KeyPackage,
}

impl Signer {
    pub fn id(&self) -> frost::Identifier {
        self.id
    }

    pub fn commit(&self) -> PendingSigner<'_> {
        let (nonces, commitments) = frost::round1::commit(self.key.signing_share(), &mut OsRng);
        PendingSigner {
            signer: self,
            nonces,
            commitments,
        }
    }
}

/// One-use nonce holder. Consuming this value prevents accidental local nonce reuse.
pub struct PendingSigner<'a> {
    signer: &'a Signer,
    nonces: frost::round1::SigningNonces,
    commitments: frost::round1::SigningCommitments,
}

impl PendingSigner<'_> {
    pub fn id(&self) -> frost::Identifier {
        self.signer.id
    }

    pub fn commitments(&self) -> frost::round1::SigningCommitments {
        self.commitments
    }

    pub fn sign(
        self,
        action: &OrderAction,
        now: u64,
        package: &frost::SigningPackage,
    ) -> Result<frost::round2::SignatureShare, DemoError> {
        self.sign_message(&action.message()?, action.expires_at, now, package)
    }

    pub fn sign_v2(
        self,
        action: &ApprovalActionV2,
        now: u64,
        package: &frost::SigningPackage,
    ) -> Result<frost::round2::SignatureShare, DemoError> {
        self.sign_message(&action.message()?, action.expires_at, now, package)
    }

    fn sign_message(
        self,
        message: &[u8],
        expires_at: u64,
        now: u64,
        package: &frost::SigningPackage,
    ) -> Result<frost::round2::SignatureShare, DemoError> {
        if expires_at <= now {
            return Err(DemoError::Expired);
        }
        if package.message() != message {
            return Err(DemoError::WrongAction);
        }
        Ok(frost::round2::sign(
            package,
            &self.nonces,
            &self.signer.key,
        )?)
    }
}

pub struct GroupPublic {
    package: frost::keys::PublicKeyPackage,
}

impl GroupPublic {
    pub fn verify(
        &self,
        action: &OrderAction,
        signature: &frost::Signature,
    ) -> Result<(), DemoError> {
        self.package
            .verifying_key()
            .verify(&action.message()?, signature)
            .map_err(|_| DemoError::InvalidSignature)
    }

    pub fn verify_v2(
        &self,
        action: &ApprovalActionV2,
        signature: &frost::Signature,
    ) -> Result<(), DemoError> {
        self.package
            .verifying_key()
            .verify(&action.message()?, signature)
            .map_err(|_| DemoError::InvalidSignature)
    }

    /// Raw group public key bytes (32 bytes) for trusted configuration.
    pub fn public_key_bytes(&self) -> Result<Vec<u8>, DemoError> {
        self.package
            .verifying_key()
            .serialize()
            .map_err(|_| DemoError::Frost)
    }
}

/// Explicit trusted-dealer setup for this demo only. Return values must be separated by owner.
pub fn trusted_dealer_setup() -> Result<(Vec<Signer>, GroupPublic), DemoError> {
    let (shares, package) =
        frost::keys::generate_with_dealer(3, 2, frost::keys::IdentifierList::Default, &mut OsRng)?;
    let mut signers = Vec::with_capacity(3);
    for (id, share) in shares {
        signers.push(Signer {
            id,
            key: frost::keys::KeyPackage::try_from(share)?,
        });
    }
    Ok((signers, GroupPublic { package }))
}

/// Coordinator sees commitments and shares, never signer keys. Caller supplies two distinct signers.
pub fn sign_action(
    action: &OrderAction,
    now: u64,
    pending: Vec<PendingSigner<'_>>,
    public: &GroupPublic,
) -> Result<frost::Signature, DemoError> {
    if action.expires_at <= now {
        return Err(DemoError::Expired);
    }
    if pending.len() < 2 {
        return Err(DemoError::TooFewSigners);
    }
    let mut commitments = BTreeMap::new();
    for signer in &pending {
        if commitments
            .insert(signer.id(), signer.commitments())
            .is_some()
        {
            return Err(DemoError::DuplicateSigner);
        }
    }
    let package = frost::SigningPackage::new(commitments, &action.message()?);
    let mut shares = BTreeMap::new();
    for signer in pending {
        let id = signer.id();
        shares.insert(id, signer.sign(action, now, &package)?);
    }
    let signature = frost::aggregate(&package, &shares, &public.package)?;
    public.verify(action, &signature)?;
    Ok(signature)
}

/// V2 equivalent of :func:`sign_action` for the versioned approval action.
pub fn sign_action_v2(
    action: &ApprovalActionV2,
    now: u64,
    pending: Vec<PendingSigner<'_>>,
    public: &GroupPublic,
) -> Result<frost::Signature, DemoError> {
    if action.expires_at <= now {
        return Err(DemoError::Expired);
    }
    if pending.len() < 2 {
        return Err(DemoError::TooFewSigners);
    }
    let mut commitments = BTreeMap::new();
    for signer in &pending {
        if commitments
            .insert(signer.id(), signer.commitments())
            .is_some()
        {
            return Err(DemoError::DuplicateSigner);
        }
    }
    let package = frost::SigningPackage::new(commitments, &action.message()?);
    let mut shares = BTreeMap::new();
    for signer in pending {
        let id = signer.id();
        shares.insert(id, signer.sign_v2(action, now, &package)?);
    }
    let signature = frost::aggregate(&package, &shares, &public.package)?;
    public.verify_v2(action, &signature)?;
    Ok(signature)
}

/// Demonstrates checks immediately before acceptance. A gateway must replace this set with
/// atomic persistent state and additionally recheck grant/ancestor revocation and budget.
pub struct DemoActionGate {
    public: GroupPublic,
    accepted_actions: HashSet<(String, String, String)>,
    accepted_business_keys: HashSet<(String, String, String)>,
}

impl DemoActionGate {
    pub fn new(public: GroupPublic) -> Self {
        Self {
            public,
            accepted_actions: HashSet::new(),
            accepted_business_keys: HashSet::new(),
        }
    }

    pub fn accept(
        &mut self,
        action: &OrderAction,
        signature: &frost::Signature,
        now: u64,
    ) -> Result<(), DemoError> {
        if action.expires_at <= now {
            return Err(DemoError::Expired);
        }
        self.public.verify(action, signature)?;
        let action_key = (
            action.tenant_id.clone(),
            action.task_id.clone(),
            action.action_id.clone(),
        );
        let business_key = (
            action.tenant_id.clone(),
            action.task_id.clone(),
            action.idempotency_key.clone(),
        );
        if self.accepted_actions.contains(&action_key)
            || self.accepted_business_keys.contains(&business_key)
        {
            return Err(DemoError::AlreadyAccepted);
        }
        self.accepted_actions.insert(action_key);
        self.accepted_business_keys.insert(business_key);
        Ok(())
    }
}
