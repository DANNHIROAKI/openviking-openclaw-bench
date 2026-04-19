## Quick Start

```bash
git clone https://github.com/DANNHIROAKI/openclaw-openviking-doubao
cd openclaw-openviking-doubao
export VOLCANO_ENGINE_API_KEY='Your Doubao API Key'   # https://console.volcengine.com/ark
bash scripts/bootstrap.sh
openclaw dashboard --no-open

openclaw config get plugins.slots.contextEngine
openclaw plugins inspect openviking
openclaw logs --follow
tail -f ~/.openviking/data/log/openviking.log
```
