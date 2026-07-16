window.addEventListener("message", (event) => {
  if (event.origin === "http://localhost:4200") console.log(event.data.type);
});
