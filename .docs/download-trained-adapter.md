# Download Trained Adapter From Server

この手順は、実環境サーバーで作成した学習成果物を、ローカルPCへダウンロードするためのものです。実IPアドレスは資料に残さず、`<SERVER_IP>` と表記します。

## 対象成果物

今回のFine-tuning成果物は、base model全体ではなくLoRA adapterです。サーバー上では以下に保存されています。

```text
~/git-archaeologist/outputs/sft/react-react-qwen3-8b-lowvram/
```

圧縮済みアーカイブは以下です。

```text
~/git-archaeologist/outputs/sft/react-react-qwen3-8b-lowvram.tar.gz
```

通常は、この `.tar.gz` だけをローカルへコピーすれば十分です。

## サーバー上の場所を確認する

まず、実環境サーバーへSSHログインし、学習成果物ディレクトリが存在することを確認します。

```bash
ssh taira@<SERVER_IP>
cd ~/git-archaeologist
ls -lah outputs/sft/react-react-qwen3-8b-lowvram
```

最低限、以下のファイルがあればLoRA adapterとして利用できます。

```text
outputs/sft/react-react-qwen3-8b-lowvram/adapter_model.safetensors
outputs/sft/react-react-qwen3-8b-lowvram/adapter_config.json
outputs/sft/react-react-qwen3-8b-lowvram/training_manifest.json
```

## サーバー上で圧縮する

まだ `.tar.gz` を作っていない場合は、サーバー上で以下を実行します。

```bash
cd ~/git-archaeologist
tar -czf outputs/sft/react-react-qwen3-8b-lowvram.tar.gz \
  -C outputs/sft react-react-qwen3-8b-lowvram
```

このコマンドは、以下のディレクトリを:

```text
~/git-archaeologist/outputs/sft/react-react-qwen3-8b-lowvram/
```

以下の1ファイルへ圧縮します。

```text
~/git-archaeologist/outputs/sft/react-react-qwen3-8b-lowvram.tar.gz
```

作成後、サーバー上でサイズを確認します。

```bash
ls -lh outputs/sft/react-react-qwen3-8b-lowvram.tar.gz
```

## ローカル側の保存先を作る

ローカルPCのPowerShellで実行します。

```powershell
cd C:\Users\tkoya\Documents\llm-tuning-lab
New-Item -ItemType Directory -Force .\outputs\sft
```

## scpでダウンロードする

ローカルPCのPowerShellで実行します。`<SERVER_IP>` は実環境サーバーのIPアドレスに置き換えます。

```powershell
scp "taira@<SERVER_IP>:~/git-archaeologist/outputs/sft/react-react-qwen3-8b-lowvram.tar.gz" ".\outputs\sft\react-react-qwen3-8b-lowvram.tar.gz"
```

パスワードを聞かれたら、サーバーへSSHログインするときと同じユーザー `taira` のパスワードを入力します。

## ダウンロード確認

```powershell
Get-Item ".\outputs\sft\react-react-qwen3-8b-lowvram.tar.gz"
```

ファイルサイズが表示されれば、ローカルへのコピーは完了です。

## ローカルで展開する

必要に応じて展開します。

```powershell
tar -xzf ".\outputs\sft\react-react-qwen3-8b-lowvram.tar.gz" -C ".\outputs\sft"
```

展開後、以下のようなファイルが存在すればLoRA adapterとして利用できます。

```text
outputs/sft/react-react-qwen3-8b-lowvram/adapter_model.safetensors
outputs/sft/react-react-qwen3-8b-lowvram/adapter_config.json
outputs/sft/react-react-qwen3-8b-lowvram/training_manifest.json
```

## よくあるエラー

### ローカル保存先がない

```text
open local ".../outputs/sft/react-react-qwen3-8b-lowvram.tar.gz": No such file or directory
```

対処:

```powershell
New-Item -ItemType Directory -Force ".\outputs\sft"
```

### パスワードが違う

```text
Permission denied, please try again.
```

対処:

```powershell
ssh taira@<SERVER_IP>
```

でログインできるか確認します。SSHログインできない場合、`scp` でもコピーできません。

### サーバー側にアーカイブがない

サーバーへSSHログインして、以下を確認します。

```bash
ls -lh ~/git-archaeologist/outputs/sft/react-react-qwen3-8b-lowvram.tar.gz
```

存在しない場合は、サーバー上で作成します。

```bash
tar -czf outputs/sft/react-react-qwen3-8b-lowvram.tar.gz \
  -C outputs/sft react-react-qwen3-8b-lowvram
```

## 注意

このアーカイブはGit管理しません。`outputs/` は成果物置き場であり、LoRA adapterやcheckpointはリポジトリへコミットしない方針です。
