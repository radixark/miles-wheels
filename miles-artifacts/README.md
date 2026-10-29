# miles-artifacts

Test fixtures for [radixark/miles](https://github.com/radixark/miles), moved here from
`yueming-yuan/miles-artifacts`.

## loss_snapshots

Expected outputs of `tests/fast/backends/training_utils/loss/test_loss_snapshot.py`: each
`<config>.pt` holds that config's inputs and the outputs and logits gradients of the loss
functions. miles pins the commit of this repo it reads them from, so a change here takes
effect only when miles bumps that pin.

A miles change that moves loss numerics on purpose regenerates the affected snapshots from
their saved inputs, lands them here, and bumps the pin in the same miles PR.
`grpo_chunked_temp_b2.pt` and `sft_chunked_b2.pt` were regenerated for radixark/miles#4315
(the log-prob gradient is now fp32, not rounded to bf16); the rest are unchanged.
