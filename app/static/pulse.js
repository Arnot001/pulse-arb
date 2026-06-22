<script>
    const scanForm = document.querySelector(
        'form[action="/"]'
    );

    if (scanForm) {

        scanForm.addEventListener(
            "submit",
            () => {

                const button =
                    document.getElementById(
                        "scanButton"
                    );

                if (button) {

                    button.innerText =
                        "SCANNING LIVE...";

                    button.disabled = true;

                    button.classList.add(
                        "scanning"
                    );
                }
            }
        );
    }
</script>