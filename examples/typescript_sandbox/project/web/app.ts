import { runWorkflow } from "@vibeflow/workflow";

const xInput = document.querySelector<HTMLInputElement>("#x");
const addendInput = document.querySelector<HTMLInputElement>("#a");
const subtrahendInput = document.querySelector<HTMLInputElement>("#b");
const button = document.querySelector<HTMLButtonElement>("#run");
const output = document.querySelector<HTMLOutputElement>("#output");

if (!xInput || !addendInput || !subtrahendInput || !button || !output) {
  throw new Error("TypeScript sandbox page is missing required elements");
}

button.addEventListener("click", async () => {
  const result = await runWorkflow({
    x: Number(xInput.value),
    a: Number(addendInput.value),
    b: Number(subtrahendInput.value),
  });
  output.textContent = String(result.result);
});
