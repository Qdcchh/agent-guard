//! Process-separated CLI for a local teaching demo. Use a private WSL filesystem directory.
use frost_ed25519 as frost;
use rand::rngs::OsRng;
use serde::{Deserialize, Serialize, de::DeserializeOwned};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::env;
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

use agent_guard_threshold_demo::{AnyAction, ApprovalActionV2, ApprovalActionV3, OrderAction};

#[derive(Serialize, Deserialize)]
struct ShareFile {
    id: frost::Identifier,
    key: frost::keys::KeyPackage,
}

#[derive(Serialize, Deserialize)]
struct NonceFile {
    id: frost::Identifier,
    nonces: frost::round1::SigningNonces,
    commitments: frost::round1::SigningCommitments,
}

#[derive(Serialize, Deserialize)]
struct CommitmentFile {
    id: frost::Identifier,
    commitments: frost::round1::SigningCommitments,
}

#[derive(Serialize, Deserialize)]
struct SignatureShareFile {
    id: frost::Identifier,
    share: frost::round2::SignatureShare,
}

fn default_tool_version() -> String {
    "1".into()
}

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct SignerPolicy {
    version: u8,
    domain: String,
    approved_action_id: String,
    approved_message_sha256: String,
    tenant_id: String,
    task_id: String,
    root_grant_id: String,
    grant_id: String,
    holder_client_id: String,
    holder_kid: String,
    audience: String,
    tool_id: String,
    policy_version: u32,
    key_epoch: u32,
    currency: String,
    max_amount_fen: u64,
    canonical_params_sha256: String,
    #[serde(default = "default_tool_version")]
    tool_version: String,
    #[serde(default)]
    path_grant_ids: Vec<String>,
}

impl SignerPolicy {
    fn for_domain(domain: &str, action: &AnyAction) -> Result<Self, Box<dyn std::error::Error>> {
        Ok(Self {
            version: 1,
            domain: domain.into(),
            approved_action_id: action.action_id().into(),
            approved_message_sha256: hex::encode(Sha256::digest(action.message()?)),
            tenant_id: action.tenant_id().into(),
            task_id: action.task_id().into(),
            root_grant_id: action.root_grant_id().into(),
            grant_id: action.grant_id().into(),
            holder_client_id: action.holder_client_id().into(),
            holder_kid: action.holder_kid().into(),
            audience: action.audience().into(),
            tool_id: action.tool_id().into(),
            policy_version: action.policy_version(),
            key_epoch: action.key_epoch(),
            currency: action.currency().into(),
            max_amount_fen: action.amount_fen(),
            canonical_params_sha256: action.canonical_params_sha256().into(),
            tool_version: action.tool_version().into(),
            path_grant_ids: action.path_grant_ids(),
        })
    }

    fn approve(&self, action: &AnyAction) -> Result<(), Box<dyn std::error::Error>> {
        if self.version != 1
            || self.approved_action_id != action.action_id()
            || self.approved_message_sha256 != hex::encode(Sha256::digest(action.message()?))
        {
            return Err("signer has no authenticated local approval for action".into());
        }
        let domain_ok = match self.domain.as_str() {
            "authorization" => {
                self.tenant_id == action.tenant_id()
                    && self.task_id == action.task_id()
                    && self.root_grant_id == action.root_grant_id()
                    && self.grant_id == action.grant_id()
                    && self.holder_client_id == action.holder_client_id()
                    && self.holder_kid == action.holder_kid()
                    && self.audience == action.audience()
                    && self.tool_id == action.tool_id()
                    && self.tool_version == action.tool_version()
                    && self.path_grant_ids == action.path_grant_ids()
                    && self.policy_version == action.policy_version()
                    && self.key_epoch == action.key_epoch()
            }
            "finance" => {
                self.currency == action.currency() && action.amount_fen() <= self.max_amount_fen
            }
            "procurement" => self.canonical_params_sha256 == action.canonical_params_sha256(),
            _ => false,
        };
        if !domain_ok {
            return Err("signer domain policy denied action".into());
        }
        Ok(())
    }
}

#[derive(Serialize)]
struct PublicTestVectorV1<'a> {
    test_only: bool,
    algorithm: &'static str,
    action: &'a OrderAction,
    group_public_key_hex: String,
    signature_hex: String,
    message_sha256: String,
}

#[derive(Serialize)]
struct PublicTestVectorV2<'a> {
    test_only: bool,
    algorithm: &'static str,
    action: &'a ApprovalActionV2,
    group_public_key_hex: String,
    signature_hex: String,
    message_sha256: String,
}

#[derive(Serialize)]
struct PublicTestVectorV3<'a> {
    test_only: bool,
    algorithm: &'static str,
    action: &'a ApprovalActionV3,
    group_public_key_hex: String,
    signature_hex: String,
    message_sha256: String,
}

fn read<T: DeserializeOwned>(path: impl AsRef<Path>) -> Result<T, Box<dyn std::error::Error>> {
    Ok(serde_json::from_slice(&fs::read(path)?)?)
}

fn write_new<T: Serialize>(
    path: impl AsRef<Path>,
    value: &T,
) -> Result<(), Box<dyn std::error::Error>> {
    write_new_raw(path, &serde_json::to_vec(value)?)
}

fn write_new_raw(path: impl AsRef<Path>, raw: &[u8]) -> Result<(), Box<dyn std::error::Error>> {
    let mut options = OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    let mut file = options.open(path)?;
    file.write_all(raw)?;
    file.sync_all()?;
    Ok(())
}

fn now() -> Result<u64, Box<dyn std::error::Error>> {
    Ok(SystemTime::now().duration_since(UNIX_EPOCH)?.as_secs())
}

fn require_unexpired(action: &AnyAction) -> Result<(), Box<dyn std::error::Error>> {
    if action.expires_at() <= now()? {
        return Err("action expired".into());
    }
    Ok(())
}

fn arg(args: &[String], at: usize) -> Result<&str, Box<dyn std::error::Error>> {
    Ok(args.get(at).ok_or("missing argument")?)
}

fn share_path(dir: &str) -> PathBuf {
    Path::new(dir).join("share.json")
}

fn session_token(session_dir: &str) -> String {
    hex::encode(Sha256::digest(session_dir.as_bytes()))[..16].to_string()
}

fn nonce_path(dir: &str, label: &str, session_dir: &str) -> PathBuf {
    Path::new(dir).join(format!("nonce-{label}-{}.json", session_token(session_dir)))
}

fn spent_nonce_path(dir: &str, label: &str, session_dir: &str) -> PathBuf {
    Path::new(dir).join(format!(
        "nonce-{label}-{}.spent",
        session_token(session_dir)
    ))
}

fn commitment_path(dir: &str, label: &str) -> PathBuf {
    Path::new(dir).join(format!("commitment-{label}.json"))
}

fn signature_share_path(dir: &str, label: &str) -> PathBuf {
    Path::new(dir).join(format!("signature-share-{label}.json"))
}

fn run(args: &[String]) -> Result<(), Box<dyn std::error::Error>> {
    match arg(args, 1)? {
        "setup" => {
            let dir = arg(args, 2)?;
            let action: AnyAction = read(arg(args, 3)?)?;
            action.message()?;
            fs::create_dir(dir)?;
            #[cfg(unix)]
            {
                use std::os::unix::fs::PermissionsExt;
                fs::set_permissions(dir, fs::Permissions::from_mode(0o700))?;
            }
            let (shares, public) = frost::keys::generate_with_dealer(
                3,
                2,
                frost::keys::IdentifierList::Default,
                &mut OsRng,
            )?;
            write_new(Path::new(dir).join("public.json"), &public)?;
            for (index, (id, share)) in shares.into_iter().enumerate() {
                let key = frost::keys::KeyPackage::try_from(share)?;
                let owner_dir = Path::new(dir).join(format!("signer-{}", index + 1));
                fs::create_dir(&owner_dir)?;
                #[cfg(unix)]
                {
                    use std::os::unix::fs::PermissionsExt;
                    fs::set_permissions(&owner_dir, fs::Permissions::from_mode(0o700))?;
                }
                write_new(owner_dir.join("share.json"), &ShareFile { id, key })?;
                let domain = ["authorization", "finance", "procurement"][index];
                write_new(
                    owner_dir.join("policy.json"),
                    &SignerPolicy::for_domain(domain, &action)?,
                )?;
            }
        }
        "round1" => {
            let key_dir = arg(args, 2)?;
            let label = arg(args, 3)?;
            let session_dir = arg(args, 4)?;
            let signer: ShareFile = read(share_path(key_dir))?;
            let (nonces, commitments) =
                frost::round1::commit(signer.key.signing_share(), &mut OsRng);
            write_new(
                nonce_path(key_dir, label, session_dir),
                &NonceFile {
                    id: signer.id,
                    nonces,
                    commitments,
                },
            )?;
            write_new(
                commitment_path(session_dir, label),
                &CommitmentFile {
                    id: signer.id,
                    commitments,
                },
            )?;
        }
        "prepare" => {
            let action: AnyAction = read(arg(args, 2)?)?;
            require_unexpired(&action)?;
            let session_dir = arg(args, 3)?;
            let labels = [arg(args, 4)?, arg(args, 5)?];
            let mut commitments = BTreeMap::new();
            for label in labels {
                let artifact: CommitmentFile = read(commitment_path(session_dir, label))?;
                if commitments
                    .insert(artifact.id, artifact.commitments)
                    .is_some()
                {
                    return Err("duplicate signer".into());
                }
            }
            let package = frost::SigningPackage::new(commitments, &action.message()?);
            write_new(Path::new(session_dir).join("package.json"), &package)?;
        }
        "round2" => {
            let key_dir = arg(args, 2)?;
            let label = arg(args, 3)?;
            let action: AnyAction = read(arg(args, 4)?)?;
            require_unexpired(&action)?;
            let session_dir = arg(args, 5)?;
            let signer: ShareFile = read(share_path(key_dir))?;
            let spent = spent_nonce_path(key_dir, label, session_dir);
            if spent.exists() {
                return Err("nonce already consumed or aborted".into());
            }
            fs::rename(nonce_path(key_dir, label, session_dir), &spent)?;
            let private: NonceFile = read(&spent)?;
            let policy: SignerPolicy = read(Path::new(key_dir).join("policy.json"))?;
            policy.approve(&action)?;
            let package: frost::SigningPackage = read(Path::new(session_dir).join("package.json"))?;
            if signer.id != private.id
                || *package.message() != action.message()?
                || package.signing_commitment(&signer.id) != Some(private.commitments)
            {
                return Err("signing package does not match this action and nonce".into());
            }
            let share = frost::round2::sign(&package, &private.nonces, &signer.key)?;
            write_new(
                signature_share_path(session_dir, label),
                &SignatureShareFile {
                    id: signer.id,
                    share,
                },
            )?;
            fs::remove_file(spent)?;
        }
        "aggregate" => {
            let action: AnyAction = read(arg(args, 2)?)?;
            require_unexpired(&action)?;
            let public: frost::keys::PublicKeyPackage = read(arg(args, 3)?)?;
            let session_dir = arg(args, 4)?;
            let labels = [arg(args, 5)?, arg(args, 6)?];
            let package: frost::SigningPackage = read(Path::new(session_dir).join("package.json"))?;
            if *package.message() != action.message()? {
                return Err("wrong action".into());
            }
            let mut shares = BTreeMap::new();
            for label in labels {
                let artifact: SignatureShareFile = read(signature_share_path(session_dir, label))?;
                if shares.insert(artifact.id, artifact.share).is_some() {
                    return Err("duplicate signer".into());
                }
            }
            if shares.len() < 2 {
                return Err("fewer than two signers".into());
            }
            let signature = frost::aggregate(&package, &shares, &public)?;
            match &action {
                AnyAction::V1(value) => {
                    public
                        .verifying_key()
                        .verify(&value.message()?, &signature)?;
                }
                AnyAction::V2(value) => {
                    public
                        .verifying_key()
                        .verify(&value.message()?, &signature)?;
                }
                AnyAction::V3(value) => {
                    public
                        .verifying_key()
                        .verify(&value.message()?, &signature)?;
                }
            }
            write_new(Path::new(session_dir).join("signature.json"), &signature)?;
        }
        "enroll" => {
            // Test/demo convenience: dealer setup without owner policies. The
            // process-separated `setup` command remains the teaching flow.
            let dir = arg(args, 2)?;
            fs::create_dir(dir)?;
            #[cfg(unix)]
            {
                use std::os::unix::fs::PermissionsExt;
                fs::set_permissions(dir, fs::Permissions::from_mode(0o700))?;
            }
            let (shares, public) = frost::keys::generate_with_dealer(
                3,
                2,
                frost::keys::IdentifierList::Default,
                &mut OsRng,
            )?;
            write_new(Path::new(dir).join("public.json"), &public)?;
            write_new_raw(
                Path::new(dir).join("public-key-hex.txt"),
                hex::encode(public.verifying_key().serialize()?).as_bytes(),
            )?;
            for (index, (id, share)) in shares.into_iter().enumerate() {
                let key = frost::keys::KeyPackage::try_from(share)?;
                let owner_dir = Path::new(dir).join(format!("signer-{}", index + 1));
                fs::create_dir(&owner_dir)?;
                #[cfg(unix)]
                {
                    use std::os::unix::fs::PermissionsExt;
                    fs::set_permissions(&owner_dir, fs::Permissions::from_mode(0o700))?;
                }
                write_new(owner_dir.join("share.json"), &ShareFile { id, key })?;
            }
        }
        "sign-quorum" => {
            // One-process 2-of-3 signer used only by the local demo and tests.
            // It exercises real FROST round1/round2/aggregate with two distinct
            // shares; it is not the process-separated teaching flow.
            let dir = arg(args, 2)?;
            let signature_out = arg(args, 3)?;
            let action: AnyAction = read(arg(args, 4)?)?;
            require_unexpired(&action)?;
            let public: frost::keys::PublicKeyPackage = read(Path::new(dir).join("public.json"))?;
            let labels: Vec<String> = args[5..].to_vec();
            let labels = if labels.is_empty() {
                vec!["signer-1".to_string(), "signer-2".to_string()]
            } else {
                labels
            };
            let mut signers = Vec::new();
            for label in &labels {
                let owner_dir = Path::new(dir).join(label);
                let signer: ShareFile = read(share_path(&owner_dir.to_string_lossy()))?;
                signers.push(signer);
            }
            // Build round-one state from the loaded shares, rejecting duplicate
            // participants before any share is produced.
            let mut commitments = BTreeMap::new();
            let mut nonces = Vec::new();
            for signer in &signers {
                let (nonce, commitment) =
                    frost::round1::commit(signer.key.signing_share(), &mut OsRng);
                if commitments.insert(signer.id, commitment).is_some() {
                    return Err("duplicate signer".into());
                }
                nonces.push((signer.id, nonce, signer.key.clone()));
            }
            if commitments.len() < 2 {
                return Err("fewer than two signers".into());
            }
            let package = frost::SigningPackage::new(commitments, &action.message()?);
            let mut shares = BTreeMap::new();
            for (id, nonce, key) in &nonces {
                let share = frost::round2::sign(&package, nonce, key)?;
                shares.insert(*id, share);
            }
            let signature = frost::aggregate(&package, &shares, &public)?;
            match &action {
                AnyAction::V1(value) => {
                    public
                        .verifying_key()
                        .verify(&value.message()?, &signature)?;
                }
                AnyAction::V2(value) => {
                    public
                        .verifying_key()
                        .verify(&value.message()?, &signature)?;
                }
                AnyAction::V3(value) => {
                    public
                        .verifying_key()
                        .verify(&value.message()?, &signature)?;
                }
            }
            write_new(signature_out, &signature)?;
        }
        "verify-quorum" => {
            let action: AnyAction = read(arg(args, 2)?)?;
            require_unexpired(&action)?;
            let public: frost::keys::PublicKeyPackage = read(arg(args, 3)?)?;
            let signature: frost::Signature = read(arg(args, 4)?)?;
            match &action {
                AnyAction::V1(value) => {
                    public
                        .verifying_key()
                        .verify(&value.message()?, &signature)?;
                }
                AnyAction::V2(value) => {
                    public
                        .verifying_key()
                        .verify(&value.message()?, &signature)?;
                }
                AnyAction::V3(value) => {
                    public
                        .verifying_key()
                        .verify(&value.message()?, &signature)?;
                }
            }
            println!("verified");
        }
        "abort" => {
            let key_dir = arg(args, 2)?;
            let label = arg(args, 3)?;
            let session_dir = arg(args, 4)?;
            let spent = spent_nonce_path(key_dir, label, session_dir);
            if spent.exists() {
                return Err("nonce already consumed or aborted".into());
            }
            fs::rename(nonce_path(key_dir, label, session_dir), spent)?;
        }
        "verify" => {
            let action: AnyAction = read(arg(args, 2)?)?;
            require_unexpired(&action)?;
            let public: frost::keys::PublicKeyPackage = read(arg(args, 3)?)?;
            let signature: frost::Signature = read(arg(args, 4)?)?;
            match &action {
                AnyAction::V1(value) => {
                    public
                        .verifying_key()
                        .verify(&value.message()?, &signature)?;
                }
                AnyAction::V2(value) => {
                    public
                        .verifying_key()
                        .verify(&value.message()?, &signature)?;
                }
                AnyAction::V3(value) => {
                    public
                        .verifying_key()
                        .verify(&value.message()?, &signature)?;
                }
            }
            println!("verified");
        }
        "export-vector" => {
            let action: AnyAction = read(arg(args, 2)?)?;
            let public: frost::keys::PublicKeyPackage = read(arg(args, 3)?)?;
            let signature: frost::Signature = read(arg(args, 4)?)?;
            let message = action.message()?;
            public.verifying_key().verify(&message, &signature)?;
            let group_public_key_hex = hex::encode(public.verifying_key().serialize()?);
            let signature_hex = hex::encode(signature.serialize()?);
            let message_sha256 = hex::encode(Sha256::digest(message));
            match &action {
                AnyAction::V1(value) => write_new(
                    arg(args, 5)?,
                    &PublicTestVectorV1 {
                        test_only: true,
                        algorithm: "FROST-Ed25519/2-of-3",
                        action: value,
                        group_public_key_hex,
                        signature_hex,
                        message_sha256,
                    },
                )?,
                AnyAction::V2(value) => write_new(
                    arg(args, 5)?,
                    &PublicTestVectorV2 {
                        test_only: true,
                        algorithm: "FROST-Ed25519/2-of-3",
                        action: value,
                        group_public_key_hex,
                        signature_hex,
                        message_sha256,
                    },
                )?,
                AnyAction::V3(value) => write_new(
                    arg(args, 5)?,
                    &PublicTestVectorV3 {
                        test_only: true,
                        algorithm: "FROST-Ed25519/2-of-3",
                        action: value,
                        group_public_key_hex,
                        signature_hex,
                        message_sha256,
                    },
                )?,
            }
        }
        _ => return Err("unknown command".into()),
    }
    Ok(())
}

fn main() {
    let args: Vec<String> = env::args().collect();
    if let Err(error) = run(&args) {
        eprintln!("threshold demo rejected: {error}");
        std::process::exit(1);
    }
}
