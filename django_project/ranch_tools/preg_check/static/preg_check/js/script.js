document.addEventListener('DOMContentLoaded', function() {
	// Function definitions
    //
    function clearBirthYearWhenSearchIdChanges() {
        var searchInput = document.getElementById("id_search_ear_tag_id");
        searchInput.addEventListener('input', function() {
            document.querySelectorAll('input[name="search_birth_year"]').forEach(item => {
                item.checked = false;
            });
        });
    }
    clearBirthYearWhenSearchIdChanges();

    // Function for handling Edit Cow Modal
    function handleEditCowModal() {
        var modal = document.getElementById("editCowModal");
        var editButton = document.getElementById("edit-cow-btn");

        if (editButton) {
            // Show modal
            document.getElementById("edit-cow-btn").onclick = function() {
                modal.style.display = "block";
            }
        }

        // Hide modal
        window.onclick = function(event) {
            if (event.target == modal) {
                modal.style.display = "none";
            }
        }
    }

    // Function for handling Create Cow Modal
    function handleCreateCowModal() {
        var modal = document.getElementById("createCowModal");
        var createButton = document.getElementById("create-cow-btn");

        if (createButton) {
            // Show modal
            createButton.onclick = function() {
                modal.style.display = "block";
            }
        }

        // Hide modal
        window.onclick = function(event) {
            if (event.target == modal) {
                modal.style.display = "none";
            }
        }
    }

	function getCookie(name) {
		let cookieValue = null;
		if (document.cookie && document.cookie !== '') {
			const cookies = document.cookie.split(';');
			for (let i = 0; i < cookies.length; i++) {
				const cookie = cookies[i].trim();
				// Does this cookie string begin with the name we want?
				if (cookie.substring(0, name.length + 1) === (name + '=')) {
					cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
					break;
				}
			}
		}
		return cookieValue;
	}
    function updatePreviousPregcheckList() {
        const content = document.getElementById('previous-pregcheck-content');
        content.innerHTML = '';
        fetch(previousPregcheckUrl)
            .then(response => response.json())
            .then(data => {
                
                // Create header container
                const headerContainer = document.createElement('div');
                headerContainer.className = 'header-container';
                content.appendChild(headerContainer);

                // Create toggle icon
                const toggleIcon = document.createElement('span');
                toggleIcon.className = 'toggle-icon';
                toggleIcon.innerHTML = '▼'; // Unicode down-pointing triangle
                headerContainer.appendChild(toggleIcon);

                // Create header text
                const headerText = document.createElement('span');
                headerText.className = 'header-text';
                headerText.textContent = 'Previous Pregchecks';
                headerContainer.appendChild(headerText);

                // Create a container for the pregcheck entries
                const entriesContainer = document.createElement('div');
                entriesContainer.id = 'pregcheck-entries';
                content.appendChild(entriesContainer);

                // Toggle functionality
                let isVisible = true;
                headerContainer.onclick = () => {
                    isVisible = !isVisible;
                    entriesContainer.style.display = isVisible ? 'block' : 'none';
                    toggleIcon.innerHTML = isVisible ? '▼' : '▶'; // Change triangle direction
                    headerText.textContent = isVisible ? 'Previous Pregchecks' : 'Previous Pregchecks';
                };

                data.pregchecks.forEach((p, index) => {
                    let entryBox = document.createElement('div');
                    entryBox.className = 'entry-box';
                    entryBox.innerHTML = `
                        <div class="entry-item"><strong>Ear Tag ID:</strong> ${p.ear_tag_id}</div>
                        <div class="entry-item"><strong>Pregnant:</strong> ${p.is_pregnant ? 'Yes' : 'No'}</div>
                    `;
                    
                    // Alternating background color
                    entryBox.classList.add(index % 2 === 0 ? 'entry-box-even' : 'entry-box-odd');
                    
                    // Hover effects and click functionality
                    entryBox.style.cursor = 'pointer';
                    // entryBox.onclick = () => populatePregcheckForm(p);
                    entryBox.onclick = () => populateEditModal(p);
                    
                    entriesContainer.appendChild(entryBox);
                });
            })
            .catch(error => {
                const errMsg = 'Error fetching previous pregchecks';
                console.error(errMsg);
                content.innerHTML = errMsg;
            });
    }

    // function populatePregcheckForm(pregcheckData) {
    //     // Populate text inputs
    //     console.log('populate pregcheck form funk')
    //     if (isRFId(pregcheckData.cow_id)) {
    //         document.getElementById('id_pregcheck_rfid').value = pregcheckData.cow_id;
    //     } else {
    //         document.getElementById('id_pregcheck_ear_tag_id').value = pregcheckData.cow_id;
    //     }

    //     document.getElementById('id_birth_year').value = pregcheckData.birth_year;
    //     document.getElementById('breeding_season').value = pregcheckData.breeding_season;
    //     document.getElementById('id_comments').value = pregcheckData.comments;

    //     // Set radio button for pregnancy status
    //     const isPregnantRadio = document.getElementById(pregcheckData.is_pregnant ? 'id_is_pregnant_0' : 'id_is_pregnant_1');
    //     if (isPregnantRadio) {
    //         isPregnantRadio.checked = true;
    //     }

    //     // Set checkbox for recheck
    //     document.getElementById('id_recheck').checked = pregcheckData.is_recheck;

    //     // Optionally, scroll to the form
    //     document.getElementById('pregcheck-form').scrollIntoView({ behavior: 'smooth' });
    // }

    function updateStats() {
        const content = document.getElementById('stats-content');
        const breedingSeason = document.getElementById('breeding-season-input').value;
    
        // Check if breedingSeason is numeric and has a length of 4
        if (breedingSeason.length === 4 && !isNaN(breedingSeason)) {
            fetch(pregcheckSummaryStatsUrl + '?stats_breeding_season=' + breedingSeason)
                .then(response => response.json())
                .then(data => {
                    // Create header container
                    const headerContainer = document.createElement('div');
                    headerContainer.className = 'header-container';
                    content.innerHTML = '';
                    content.appendChild(headerContainer);
    
                    // Create toggle icon
                    const toggleIcon = document.createElement('span');
                    toggleIcon.className = 'toggle-icon';
                    toggleIcon.innerHTML = '▼';
                    headerContainer.appendChild(toggleIcon);
    
                    // Create header text
                    const headerText = document.createElement('span');
                    headerText.className = 'header-text';
                    headerText.textContent = 'New Summary Stats';
                    headerContainer.appendChild(headerText);
    
                    // Create a container for the stats entries
                    const entriesContainer = document.createElement('div');
                    entriesContainer.id = 'stats-entries';
                    content.appendChild(entriesContainer);
    
                    // Toggle functionality
                    let isVisible = true;
                    headerContainer.onclick = () => {
                        isVisible = !isVisible;
                        entriesContainer.style.display = isVisible ? 'block' : 'none';
                        toggleIcon.innerHTML = isVisible ? '▼' : '▶';
                    };
    
                    // Populate stats content
                    entriesContainer.innerHTML = `
                        <p>Pregnant at 1st check: ${data.first_check_pregnant}</p>
                        <p>Recheck Pregnant: ${data.recheck_pregnant}</p>
                        <p><b>Total Pregnant: ${data.total_pregnant}</b></p>
                        <p>Open at 1st check: ${data.first_check_open}</p>
                        <p>Less recheck pregnant: -${data.recheck_pregnant}</p>
                        <p><b>Total Open: ${data.total_open}</b></p>
                        <p><b>Total Count: ${data.total_count}</b></p>
                        <p><b>Pregnancy Rate: ${data.pregnancy_rate.toFixed(2)}%</b></p>
                    `;
                })
                .catch(error => {
                    console.error('Error fetching summary stats:', error);
                    content.innerHTML = 'Error fetching summary stats.';
                });
        } else {
            content.innerHTML = 'Please provide a valid 4-digit breeding season.';
        }
    }

	function xupdateStats() {
        // Make an AJAX request to fetch the summary stats
        const statsContent = document.getElementById('stats-content');
        const breedingSeason = document.getElementById('breeding-season-input').value;

        // Check if breedingSeason is numeric and has a length of 4
        if (breedingSeason.length === 4 && !isNaN(breedingSeason)) {
            fetch(pregcheckSummaryStatsUrl + '?stats_breeding_season=' + breedingSeason)
                .then(response => response.json())
                .then(data => {
                    // Update the stats content with the fetched data
                    statsContent.innerHTML = `
                        <h2>Summary Stats</h2>
                        <p>Pregnant at 1st check: ${data.first_check_pregnant}</p>
                        <p>Recheck Pregnant: ${data.recheck_pregnant}</p>
                        <p><b>Total Pregnant: ${data.total_pregnant}</b></p>
                        <p>Open at 1st check: ${data.first_check_open}</p>
                        <p>Less recheck pregnant: -${data.recheck_pregnant}</p>
                        <p><b>Total Open: ${data.total_open}</b></p>
                        <p><b>Total Count: ${data.total_count}</b></p>
                        <p><b>Pregnancy Rate: ${data.pregnancy_rate.toFixed(2)}%</b></p>
                    `;
                })
                .catch(error => {
                    console.error('Error fetching summary stats:', error);
                    statsContent.innerHTML = 'Error fetching summary stats.';
                });
        } else {
            statsContent.innerHTML = 'Please provide a valid 4-digit breeding season.';
        }
    }

	function handleFormSubmit(event) {
		event.preventDefault(); // Prevent normal form submission
		var form = document.getElementById('pregcheck-form');
        const submitButton = form.querySelector('button[id="pregcheck-form-submit-btn"]');
        submitButton.disabled = true;

		var messageContainer = document.getElementById('message-container');
		var modal = document.getElementById('message-modal');
		var formData = new FormData(form);
     
        // Validate ear tag ID and "No ID" checkbox
        const earTagIdValue = formData.get('pregcheck_ear_tag_id').trim();
        const rfidValue = formData.get('pregcheck_rfid').trim();
        const noIdChecked = formData.get('no_id') === 'on' || formData.get('no_id') === true;
        if (!earTagIdValue && !rfidValue && !noIdChecked) {
            messageContainer.textContent = 'If Ear Tag ID and RFID is blank, you must check "No ID".';
            messageContainer.classList.add('error');
            modal.style.display = 'block';
            return;
        } else if ((earTagIdValue || rfidValue) && noIdChecked) {
            messageContainer.textContent = 'If Ear Tag ID or RFID is provided, "No ID" should not be checked.';
            messageContainer.classList.add('error');
            modal.style.display = 'block';
            return;
        }
        // If "No ID" is checked and both ear tag and rfid are blank, clear birth year input
        if (noIdChecked && !earTagIdValue && !rfidValue) {
            const birthYearInput = document.getElementById('id_birth_year');
            const formBirthYearValue = formData.get('birth_year');
            if (formBirthYearValue) {
                birthYearInput.value = '';
                formData.set('birth_year', '');
            }
        }

		var xhr = new XMLHttpRequest();
		xhr.open(form.method, form.action, true);
		xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
		xhr.onload = function() {
			if (xhr.status === 200) {
                updateStats();
                updatePreviousPregcheckList();
				// Display success message
				messageContainer.textContent = 'PregCheck created successfully';
				messageContainer.classList.add('success');
				modal.style.display = 'block';
                setTimeout(function() {
                    modal.style.display = 'none';
                    location.href = pregchecksUrl;
                }, 2000);
			} else {
				// Display error message
				messageContainer.textContent = 'Something went wrong';
				messageContainer.classList.add('error');
				modal.style.display = 'block';
                submitButton.disabled = false;
			}
		};
		xhr.onerror = function() {
			// Display error message
			messageContainer.textContent = 'Something went wrong';
			messageContainer.classList.add('error');
			modal.style.display = 'block';
            submitButton.disabled = false;
		};
		xhr.send(formData);
	}

	function handleContinueBtnClick() {
		var modal = document.getElementById('message-modal');
		modal.style.display = 'none';
	}

	function closeModal() {
		var modal = document.getElementById('message-modal');
		modal.style.display = 'none';
	}

	function closePregCheckEditModal() {
		var modal = document.getElementById('edit-modal');
		modal.style.display = 'none';
	}

	function closeEditCowModal() {
		var modal = document.getElementById('editCowModal');
		modal.style.display = 'none';
	}

	function closeCreateNewSameIdCowModal() {
		var modal = document.getElementById('createCowModal');
		modal.style.display = 'none';
	}

	function handleModalCloseBtnClick() {
		closeModal();
	}

	function handleWindowClick(event) {
		var modal = document.getElementById('message-modal');
		if (event.target === modal) {
			closeModal();
		}
	}
	
	function handleCreateAnimal() {
		const noAnimalModal = document.getElementById('no-animal-modal');
        // const noAnimaRFIDlModal = document.getElementById('no-animal-rfid-modal');
		
		function openNoAnimalModal(earTagId, rfid) {
			noAnimalModal.style.display = 'block';
			if (earTagId) {
                document.getElementById('new_ear_tag_id').value = earTagId;
            }
			if (rfid) {
                document.getElementById('new_eid').value = rfid;
            }
		}

		function closeNoAnimalModal() {
			noAnimalModal.style.display = 'none';
            // noAnimaRFIDlModal.style.display = 'none';
		}

        const earTagId = document.getElementById('id_search_ear_tag_id').value;
        const rfid = document.getElementById('id_search_rfid').value;

        if (!animalExists && (earTagId || rfid) && earTagId != 'all' && rfid != 'all') {
			openNoAnimalModal(earTagId, rfid);
		} else {
			closeNoAnimalModal();
		}

		return { openNoAnimalModal, closeNoAnimalModal };
	}
    const { closeNoAnimalModal } = handleCreateAnimal();

	// Function to populate the edit modal with data
    function populateEditModal(pregcheckData) {
        // Populate form fields in the edit modal with data from pregcheckData
        if (pregcheckData.ear_tag_id) {
            document.getElementById('edit-ear-tag-id').value = pregcheckData.ear_tag_id;
        }
        if (pregcheckData.animal_birth_year) {
            document.getElementById('edit-birth-year').value = pregcheckData.animal_birth_year;
        }
        document.getElementById('edit-check_date').value = pregcheckData.check_date;
        document.getElementById('edit-breeding-season').value = pregcheckData.breeding_season;
        document.getElementById('edit-pregcheck-id').value = pregcheckData.id;
        document.getElementById('edit-is_pregnant').value = pregcheckData.is_pregnant.toString();
        document.getElementById('edit-comments').value = pregcheckData.comments;
        document.getElementById('edit-recheck').checked = pregcheckData.recheck;
        document.getElementById('edit-should-sell').checked = pregcheckData.should_sell;        

        
        // Show the edit modal
        const editModal = document.getElementById('edit-modal');
        editModal.style.display = 'block';
    }

	// Event Listeners
    function listenToModalClosers(modalId, closers) {
        closers.forEach(selector => {
            var closerElem = document.querySelector(selector);
            if (closerElem) {
                closerElem.addEventListener('click', function() {
                    var modal = document.getElementById(modalId);
                    modal.style.display = 'none';
                });
            }
        });
    }

    // Check for Cow Existence by ear tag id
    function checkCowExistence(earTagId) {
        const resultContainer = document.getElementById('check-existing-ear-tag-result');
        resultContainer.innerHTML = ''; // Clear any existing content
    
        fetch(`/cow/exists?ear_tag_id=${earTagId}`)
            .then(response => {
                if (response.ok) {
                    return response.json();
                } else {
                    throw new Error('Error checking cow existence');
                }
            })
            .then(data => {
                if (data.exists) {
                    // Create the form element
                    const form = document.createElement('form');
                    form.method = 'POST';
                    form.action = `/cows/${earTagId}/update`;
    
                    // Add CSRF token input (if using Django)
                    const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]');
                    if (csrfToken) {
                        const csrfInput = document.createElement('input');
                        csrfInput.type = 'hidden';
                        csrfInput.name = 'csrfmiddlewaretoken';
                        csrfInput.value = csrfToken.value;
                        form.appendChild(csrfInput);
                    }
    
                    // Create and append the RFID input field
                    const rfidInput = document.createElement('input');
                    rfidInput.type = 'hidden';
                    rfidInput.name = 'eid';
                    rfidInput.value = data.rfid || ''; // Use the fetched RFID value
                    form.appendChild(rfidInput);
    
                    // Create and append the Ear Tag ID input field
                    const earTagIdInput = document.createElement('input');
                    earTagIdInput.type = 'hidden';
                    earTagIdInput.name = 'ear_tag_id';
                    earTagIdInput.value = earTagId;
                    form.appendChild(earTagIdInput);
    
                    // Create and append the Birth Year input field
                    const birthYearInput = document.createElement('input');
                    birthYearInput.type = 'hidden';
                    birthYearInput.name = 'birth_year';
                    birthYearInput.value = data.birth_year || ''; // Use the fetched Birth Year value
                    form.appendChild(birthYearInput);
    
                    // Create and append the submit button
                    const submitButton = document.createElement('button');
                    submitButton.type = 'submit';
                    submitButton.textContent = 'Update Cow';
                    form.appendChild(submitButton);
    
                    // Append the form to the result container
                    resultContainer.appendChild(form);
                } else {
                    // If the cow does not exist, show a message or other UI elements
                    const message = document.createElement('p');
                    message.textContent = 'Cow does not exist. Please create a new record.';
                    resultContainer.appendChild(message);
    
                    const createNewCowButton = document.createElement('button');
                    createNewCowButton.textContent = 'Create New Cow';
                    createNewCowButton.addEventListener('click', function () {
                        // Handle create new cow logic here
                    });
                    resultContainer.appendChild(createNewCowButton);
                }
            })
            .catch(error => {
                console.error('Error checking cow existence:', error);
            });
    }

    document.getElementById('check-existing-ear-tag-btn').addEventListener('click', function() {
        const earTagId = document.getElementById('check_existing_ear_tag_id').value;
        checkCowExistence(earTagId);
    });

    // Edit Cow
    function listenToEditCowModal() {
        listenToModalClosers('editCowModal', ['#edit-cow-modal-cancel-btn', '#editCowModal .close']);
    }
    listenToEditCowModal();

    // Handle Ear Tag Update Checkbox
    function handleAllowEarTagUpdate() {
        const checkbox = document.getElementById('allow_ear_tag_update');
        const earTagInput = document.getElementById('edit_ear_tag_id');
        
        if (checkbox) {
            checkbox.addEventListener('change', function() {
                if (this.checked) {
                    earTagInput.removeAttribute('readonly');
                } else {
                    earTagInput.setAttribute('readonly', 'readonly');
                }
            });
        }
    }
    handleAllowEarTagUpdate();


    // Edit Preg check record 
    document.querySelector('#edit-modal .close').addEventListener('click', closePregCheckEditModal);

    // Create same ID cow
    function listenToCreateSameIdCowModal() {
        listenToModalClosers('createCowModal', ['#create-cow-modal-cancel-btn', '#createCowModal .close']);
    }
    listenToCreateSameIdCowModal();

    // Create new ID cow
    document.querySelector('#no-animal-modal .close').addEventListener('click', closeNoAnimalModal);
    document.querySelector('#no-animal-rfid-modal .close').addEventListener('click', closeNoAnimalModal);
    document.getElementById('cancel-create-btn').addEventListener('click', closeNoAnimalModal);

	document.getElementById('pregcheck-form').addEventListener('submit', handleFormSubmit);
	document.querySelector('.close').addEventListener('click', handleModalCloseBtnClick);

    // Listen to Breeding Season input and update stats
    const currentBreedingSeasonInput = document.getElementById('breeding-season-input');
    currentBreedingSeasonInput.addEventListener('input', function() {
        const inputValue = this.value;
        if(inputValue && inputValue.length === 4) {
            currentBreedingSeasonInput.value = inputValue;
            fetch('/pregchecks/current-breeding-season/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                },
                body: JSON.stringify({ breeding_season: inputValue })
            })
            .then(response => response.json())
            .then(data => {
                if (data.status !== 'success') {
                    console.error("Failed to update breeding season:", data.message);
                } else {
                    document.getElementById('breeding_season').value = inputValue;
                }

            })
            .catch(error => {
                console.error("Error:", error);
            });
            updateStats();
        }
    });

    // Event listener for "edit" buttons
    document.querySelectorAll('.edit-button').forEach(button => {
        button.addEventListener('click', () => {
            const pregcheckId = button.getAttribute('data-pregcheck-id');
            // Make an AJAX request to fetch data for the selected pregcheck
            fetch(`/pregchecks/${pregcheckId}/`)
                .then(response => response.json())
                .then(data => {
                    populateEditModal(data);
                })
                .catch(error => {
                    console.error('Error fetching pregcheck data:', error);
                });
        });
    });

	// Event listener for "Save" button in the edit modal
    document.getElementById('edit-pregcheck-form').addEventListener('submit', function(event) {
        event.preventDefault(); // Prevent normal form submission
        
        const formData = new FormData(this);
        const pregcheckId = document.getElementById('edit-pregcheck-id').value;
        
        fetch(`/pregchecks/${pregcheckId}/edit/`, {
            method: 'POST',
            body: formData,
            headers: {
                'X-CSRFToken': getCookie('csrftoken'), // Include CSRF token
            },
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // Handle success (e.g., close modal, update UI)
                closePregCheckEditModal();
                location.reload();
            } else if (data.errors) {
                // Handle form errors (e.g., display error messages)
                console.error('Form errors:', data.errors);
            } else {
                // Handle other errors or unexpected responses
                console.error('Unexpected response:', data);
            }
        })
        .catch(error => {
            console.error('Error:', error);
        });
    });


	window.addEventListener('click', handleWindowClick);

	// Initial Actions
    updateStats();
    updatePreviousPregcheckList();
    handleCreateAnimal();
    handleEditCowModal();
    handleCreateCowModal();
});

