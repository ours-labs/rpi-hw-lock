# rpi-hw-lock

[English](README.md) | 日本語

`rpi-hw-lock`は、通常は長時間稼働するsystemdサービスが利用しているRaspberry Piのハードウェアへ、安全に排他的アクセスを行うための軽量なPythonライブラリです。

GPIO、SPI、I2C、UARTへアクセスするコードブロックの実行前に、指定したサービスを一時停止します。終了後は、もともと稼働していたサービスだけを再起動します。保護されたブロックで例外が発生しても、後処理を実行します。

> システムサービスを操作するライブラリです。本番デバイスで利用する前に、対象サービスの一覧とsudoers設定を十分に確認してください。

## インストール

```bash
pip install rpi-hw-lock
```

実行時の依存関係はPython標準ライブラリのみです。Python 3.9以上と、systemdを使用するLinuxが必要です。

## 使用方法

```python
from rpi_hw_lock import exclusive_hardware_access

with exclusive_hardware_access(["example-sensor.service"]):
    # Access GPIO, SPI, I2C, or UART hardware here.
    ...
# Services that were active before the block are running again here.
```

複数のサービスをまとめて制御することもできます。

```python
with exclusive_hardware_access(["service-a.service", "service-b.service"]):
    ...
```

## sudoersの設定

システムサービスの停止・起動には通常、管理者権限が必要です。必要なサービスへの必要な操作だけを許可する、限定的なsudoersルールを作成してください。

```bash
sudo visudo -f /etc/sudoers.d/rpi-hw-lock
```

専用サービスアカウントと正確なサービス名に合わせて調整する例:

```text
<service-user> ALL=(root) NOPASSWD: /usr/bin/systemctl stop example-sensor.service
<service-user> ALL=(root) NOPASSWD: /usr/bin/systemctl start example-sensor.service
```

`systemctl`への無制限なパスワード不要のアクセスを許可しないでください。

排他的アクセスを試す前に、設定を確認できます。

```python
from rpi_hw_lock import check_permissions

check_permissions(["example-sensor.service"])
```

## API

| API | 用途 |
| --- | --- |
| `exclusive_hardware_access(services, timeout=10.0, verify_stopped=True)` | 1つ以上のサービスを一時停止し、元の稼働状態へ戻します。 |
| `check_permissions(services, timeout=5.0)` | 対話なしでsudoを使える設定になっているか確認します。 |
| `is_active(service)` | サービスが現在稼働しているかを返します。 |
| `ServiceControlError` | 停止、起動、状態確認に失敗した場合に発生する例外です。 |

## 動作と制約

- もともと停止していたサービスは、コンテキスト終了時に起動しません。
- `verify_stopped=True`では、保護されたブロックの実行前に各サービスの停止を確認します。
- 通常の`systemctl stop`は、`Restart=on-failure`による失敗とは扱われません。
- 別の例外を処理している間にサービスの再起動が失敗した場合、元の例外を隠さないよう再起動失敗をログへ記録します。運用者がログを監視し、手動でサービスを復旧する必要があります。
- systemdと協調するライブラリです。対象サービス以外で同じハードウェアへアクセスするプログラムを含めた、プロセス間ロックではありません。

## 開発

```bash
python -m unittest discover -s tests -v
python -m build
python -m twine check dist/*
```

## ライセンス

MIT
