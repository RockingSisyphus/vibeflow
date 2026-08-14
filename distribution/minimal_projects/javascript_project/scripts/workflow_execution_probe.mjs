import fs from "node:fs";
import { runWorkflow } from "../build/node/workflow.js";

const input = JSON.parse(fs.readFileSync(new URL("../probe_input.json", import.meta.url), "utf8"));
const output = runWorkflow(input);
if (!Object.prototype.hasOwnProperty.call(output, "response")) {
  throw new Error("declared response output was not produced");
}
const report = {
  status: "PASS",
  result_code: "VIBEFLOW_WORKFLOW_EXECUTION_PASS",
  validation_scope: "vibeflow_workflow_execution",
  summary: "VibeFlow 工作流执行探针通过",
  checked: [
    { id: "workflow_started", label: "工作流成功启动" },
    { id: "declared_outputs", label: "声明的最终输出已经产生" },
    { id: "structural_runtime", label: "未出现结构性执行错误" }
  ],
  not_checked: [
    { id: "business_correctness", label: "业务结果正确性" },
    { id: "requirements_conformance", label: "项目需求符合性" },
    { id: "external_semantics", label: "外部接口业务语义" },
    { id: "domain_data_correctness", label: "领域数据正确性" }
  ],
  output
};
fs.mkdirSync(new URL("../run_artifacts/", import.meta.url), { recursive: true });
fs.writeFileSync(new URL("../run_artifacts/workflow_execution_report.json", import.meta.url), `${JSON.stringify(report, null, 2)}\n`);
process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
