/*
 * static/js/script.js
 * ===================
 * Vanilla JavaScript for Phase 1 — minimal, focused on:
 *   1. Showing the server start time dynamically
 *   2. Adding subtle entrance animations
 *   3. Demonstrating that the JS file is correctly loaded by Flask
 *
 * Flask serves all files inside static/ automatically.
 * No special configuration needed — just put files in static/
 * and reference them with url_for('static', filename='...') in templates.
 */

// ============================================================
// DOMContentLoaded: Waits for the HTML to fully parse before
// running any JavaScript. This is a safe place to start.
// ============================================================
document.addEventListener('DOMContentLoaded', function () {

    // --------------------------------------------------------
    // 1. Display the current date/time as the "server start time"
    //    (In later phases, this will come from the Flask backend)
    // --------------------------------------------------------
    const startTimeElement = document.getElementById('start-time');
    if (startTimeElement) {
        const now = new Date();
        const options = {
            year: 'numeric',
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
        };
        startTimeElement.textContent = now.toLocaleString('en-IN', options);
    }

    // --------------------------------------------------------
    // 2. Animate the status dot — pulse effect to show "live"
    // --------------------------------------------------------
    const statusDot = document.getElementById('status-dot');
    if (statusDot) {
        statusDot.classList.add('pulse');
    }

    // --------------------------------------------------------
    // 3. Staggered entrance animation for tech cards
    //    Respects prefers-reduced-motion
    // --------------------------------------------------------
    const prefersReducedMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const techCards = document.querySelectorAll('.tech-card');
    if (!prefersReducedMotion) {
        techCards.forEach(function (card, index) {
            card.style.opacity = '0';
            card.style.transform = 'translateY(20px)';
            setTimeout(function () {
                card.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
                card.style.opacity = '1';
                card.style.transform = 'translateY(0)';
            }, 300 + index * 150);
        });

        const serverInfo = document.getElementById('server-info-panel');
        if (serverInfo) {
            serverInfo.style.opacity = '0';
            serverInfo.style.transform = 'translateY(30px)';
            setTimeout(function () {
                serverInfo.style.transition = 'opacity 0.6s ease, transform 0.6s ease';
                serverInfo.style.opacity = '1';
                serverInfo.style.transform = 'translateY(0)';
            }, 700);
        }
    }

    // --------------------------------------------------------
    // 5. Log a confirmation to the browser console
    //    Open DevTools (F12) → Console to see this message
    // --------------------------------------------------------
    console.log('%c✅ Sports Management System', 'color: #00d4aa; font-size: 16px; font-weight: bold;');
    console.log('%cPhase 5.1: Sports Management Module Active', 'color: #888; font-size: 12px;');

    // --------------------------------------------------------
    // 6. Phase 5.1: Real-time Sports Table Search Filtering
    // --------------------------------------------------------
    const searchInput = document.getElementById('sports-search');
    const sportsTable = document.getElementById('sports-table');
    const noResultsRow = document.getElementById('no-search-results');

    if (searchInput && sportsTable) {
        searchInput.addEventListener('input', function () {
            const query = searchInput.value.toLowerCase().trim();
            const rows = sportsTable.querySelectorAll('tbody tr:not(#no-search-results)');
            let visibleCount = 0;

            rows.forEach(function (row) {
                const name = row.getAttribute('data-sport-name') || '';
                const desc = row.getAttribute('data-sport-desc') || '';
                const text = (name + ' ' + desc).toLowerCase();

                if (query === '' || text.includes(query)) {
                    row.style.display = '';
                    visibleCount++;
                } else {
                    row.style.display = 'none';
                }
            });

            if (noResultsRow) {
                noResultsRow.style.display = (visibleCount === 0 && query !== '') ? '' : 'none';
            }
        });
    }

    // --------------------------------------------------------
    // 7. Phase 5.1: Safe Delete Confirmation Dialog (Sports)
    // --------------------------------------------------------
    const deleteForms = document.querySelectorAll('.delete-sport-form');
    deleteForms.forEach(function (form) {
        form.addEventListener('submit', function (event) {
            const sportName = form.getAttribute('data-sport-name') || 'this sport';
            const confirmed = window.confirm(
                `Are you sure you want to delete "${sportName}"?\n\nThis action cannot be undone. Sports with associated teams, players, or tournaments cannot be deleted.`
            );
            if (!confirmed) {
                event.preventDefault();
            }
        });
    });

    // --------------------------------------------------------
    // 8. Phase 5.2: Real-time Teams Table Search & Sport Filter
    // --------------------------------------------------------
    const teamSearchInput = document.getElementById('teams-search');
    const teamSportFilter = document.getElementById('sport-filter');
    const teamsTable = document.getElementById('teams-table');
    const noTeamResultsRow = document.getElementById('no-team-search-results');

    if (teamsTable && (teamSearchInput || teamSportFilter)) {
        function filterTeamsTable() {
            const query = teamSearchInput ? teamSearchInput.value.toLowerCase().trim() : '';
            const selectedSportId = teamSportFilter ? teamSportFilter.value : '';
            const rows = teamsTable.querySelectorAll('tbody tr:not(#no-team-search-results)');
            let visibleCount = 0;

            rows.forEach(function (row) {
                const name = (row.getAttribute('data-team-name') || '').toLowerCase();
                const sportName = (row.getAttribute('data-sport-name') || '').toLowerCase();
                const sportId = row.getAttribute('data-sport-id') || '';

                const matchesQuery = query === '' || name.includes(query) || sportName.includes(query);
                const matchesSport = selectedSportId === '' || sportId === selectedSportId;

                if (matchesQuery && matchesSport) {
                    row.style.display = '';
                    visibleCount++;
                } else {
                    row.style.display = 'none';
                }
            });

            if (noTeamResultsRow) {
                const isFiltered = query !== '' || selectedSportId !== '';
                noTeamResultsRow.style.display = (visibleCount === 0 && isFiltered) ? '' : 'none';
            }
        }

        if (teamSearchInput) {
            teamSearchInput.addEventListener('input', filterTeamsTable);
        }
        if (teamSportFilter) {
            teamSportFilter.addEventListener('change', filterTeamsTable);
        }
    }

    // --------------------------------------------------------
    // 9. Phase 5.2: Safe Delete Confirmation Dialog (Teams)
    // --------------------------------------------------------
    const deleteTeamForms = document.querySelectorAll('.delete-team-form');
    deleteTeamForms.forEach(function (form) {
        form.addEventListener('submit', function (event) {
            const teamName = form.getAttribute('data-team-name') || 'this team';
            const confirmed = window.confirm(
                `Are you sure you want to delete "${teamName}"?\n\nThis action cannot be undone. Teams with assigned players, matches, or results cannot be deleted.`
            );
            if (!confirmed) {
                event.preventDefault();
            }
        });
    });

    // --------------------------------------------------------
    // 10. Phase 5.3: Real-time Players Table Search & Filter
    // --------------------------------------------------------
    const playerSearchInput = document.getElementById('players-search');
    const playerSportFilter = document.getElementById('player-sport-filter');
    const playerTeamFilter = document.getElementById('player-team-filter');
    const playersTable = document.getElementById('players-table');
    const noPlayerResultsRow = document.getElementById('no-player-search-results');

    if (playersTable && (playerSearchInput || playerSportFilter || playerTeamFilter)) {
        function filterPlayersTable() {
            const query = playerSearchInput ? playerSearchInput.value.toLowerCase().trim() : '';
            const selectedSportId = playerSportFilter ? playerSportFilter.value : '';
            const selectedTeamId = playerTeamFilter ? playerTeamFilter.value : '';
            const rows = playersTable.querySelectorAll('tbody tr:not(#no-player-search-results)');
            let visibleCount = 0;

            rows.forEach(function (row) {
                const name = (row.getAttribute('data-player-name') || '').toLowerCase();
                const sportName = (row.getAttribute('data-sport-name') || '').toLowerCase();
                const teamName = (row.getAttribute('data-team-name') || '').toLowerCase();
                const sportId = row.getAttribute('data-sport-id') || '';
                const teamId = row.getAttribute('data-team-id') || '';

                const matchesQuery = query === '' || name.includes(query) || sportName.includes(query) || teamName.includes(query);
                const matchesSport = selectedSportId === '' || sportId === selectedSportId;
                const matchesTeam = selectedTeamId === '' || teamId === selectedTeamId;

                if (matchesQuery && matchesSport && matchesTeam) {
                    row.style.display = '';
                    visibleCount++;
                } else {
                    row.style.display = 'none';
                }
            });

            if (noPlayerResultsRow) {
                const isFiltered = query !== '' || selectedSportId !== '' || selectedTeamId !== '';
                noPlayerResultsRow.style.display = (visibleCount === 0 && isFiltered) ? '' : 'none';
            }
        }

        if (playerSearchInput) {
            playerSearchInput.addEventListener('input', filterPlayersTable);
        }
        if (playerSportFilter) {
            playerSportFilter.addEventListener('change', filterPlayersTable);
        }
        if (playerTeamFilter) {
            playerTeamFilter.addEventListener('change', filterPlayersTable);
        }
    }

    // --------------------------------------------------------
    // 11. Phase 5.3: Safe Delete Confirmation Dialog (Players)
    // --------------------------------------------------------
    const deletePlayerForms = document.querySelectorAll('.delete-player-form');
    deletePlayerForms.forEach(function (form) {
        form.addEventListener('submit', function (event) {
            const playerName = form.getAttribute('data-player-name') || 'this player';
            const confirmed = window.confirm(
                `Are you sure you want to delete player "${playerName}"?\n\nThis action cannot be undone. Players with recorded match statistics cannot be deleted.`
            );
            if (!confirmed) {
                event.preventDefault();
            }
        });
    });

    // --------------------------------------------------------
    // 12. Phase 5.3: Dynamic Team Dropdown Filter in Player Form
    // --------------------------------------------------------
    const playerFormSport = document.getElementById('player_sport_id');
    const playerFormTeam = document.getElementById('player_team_id');

    if (playerFormSport && playerFormTeam) {
        function updateTeamOptions() {
            const selectedSport = playerFormSport.value;
            const teamOptions = playerFormTeam.querySelectorAll('option');

            teamOptions.forEach(function (opt) {
                const optSportId = opt.getAttribute('data-sport-id');
                if (!optSportId) {
                    // "Unassigned" option is always visible
                    opt.style.display = '';
                } else if (selectedSport === '' || optSportId === selectedSport) {
                    opt.style.display = '';
                } else {
                    opt.style.display = 'none';
                    if (opt.selected) {
                        playerFormTeam.value = '';
                    }
                }
            });
        }

        playerFormSport.addEventListener('change', updateTeamOptions);
        updateTeamOptions();
    }

    // --------------------------------------------------------
    // 13. Phase 5.4: Real-time Tournaments Table Search & Filter
    // --------------------------------------------------------
    const tournamentSearchInput = document.getElementById('tournaments-search');
    const tournamentSportFilter = document.getElementById('tournament-sport-filter');
    const tournamentStatusFilter = document.getElementById('tournament-status-filter');
    const tournamentsTable = document.getElementById('tournaments-table');
    const noTournamentResultsRow = document.getElementById('no-tournament-search-results');
    const tournamentsCountDisplay = document.getElementById('tournaments-count-display');

    if (tournamentsTable && (tournamentSearchInput || tournamentSportFilter || tournamentStatusFilter)) {
        function filterTournamentsTable() {
            const query = tournamentSearchInput ? tournamentSearchInput.value.toLowerCase().trim() : '';
            const selectedSportId = tournamentSportFilter ? tournamentSportFilter.value : '';
            const selectedStatus = tournamentStatusFilter ? tournamentStatusFilter.value.toLowerCase() : '';
            const rows = tournamentsTable.querySelectorAll('tbody tr:not(#no-tournament-search-results)');
            let visibleCount = 0;
            const totalCount = rows.length;

            rows.forEach(function (row) {
                const name = (row.getAttribute('data-tournament-name') || '').toLowerCase();
                const sportName = (row.getAttribute('data-sport-name') || '').toLowerCase();
                const desc = (row.getAttribute('data-tournament-desc') || '').toLowerCase();
                const sportId = row.getAttribute('data-sport-id') || '';
                const status = (row.getAttribute('data-tournament-status') || '').toLowerCase();

                const matchesQuery = query === '' || name.includes(query) || sportName.includes(query) || desc.includes(query);
                const matchesSport = selectedSportId === '' || sportId === selectedSportId;
                const matchesStatus = selectedStatus === '' || status === selectedStatus;

                if (matchesQuery && matchesSport && matchesStatus) {
                    row.style.display = '';
                    visibleCount++;
                } else {
                    row.style.display = 'none';
                }
            });

            if (noTournamentResultsRow) {
                const isFiltered = query !== '' || selectedSportId !== '' || selectedStatus !== '';
                noTournamentResultsRow.style.display = (visibleCount === 0 && isFiltered) ? '' : 'none';
            }

            if (tournamentsCountDisplay) {
                tournamentsCountDisplay.textContent = `Showing ${visibleCount} of ${totalCount} tournaments`;
            }
        }

        if (tournamentSearchInput) {
            tournamentSearchInput.addEventListener('input', filterTournamentsTable);
        }
        if (tournamentSportFilter) {
            tournamentSportFilter.addEventListener('change', filterTournamentsTable);
        }
        if (tournamentStatusFilter) {
            tournamentStatusFilter.addEventListener('change', filterTournamentsTable);
        }
    }

    // --------------------------------------------------------
    // 14. Phase 5.4: Safe Delete Confirmation Dialog (Tournaments)
    // --------------------------------------------------------
    const deleteTournamentForms = document.querySelectorAll('.delete-tournament-form');
    deleteTournamentForms.forEach(function (form) {
        form.addEventListener('submit', function (event) {
            const tournamentName = form.getAttribute('data-tournament-name') || 'this tournament';
            const confirmed = window.confirm(
                `Are you sure you want to delete tournament "${tournamentName}"?\n\nThis action cannot be undone. Tournaments with scheduled or recorded matches cannot be deleted.`
            );
            if (!confirmed) {
                event.preventDefault();
            }
        });
    });

    // --------------------------------------------------------
    // 15. Phase 5.5: Real-time Matches Table Search & Filter
    // --------------------------------------------------------
    const matchSearchInput = document.getElementById('matches-search');
    const matchTournamentFilter = document.getElementById('match-tournament-filter');
    const matchSportFilter = document.getElementById('match-sport-filter');
    const matchStatusFilter = document.getElementById('match-status-filter');
    const matchesTable = document.getElementById('matches-table');
    const noMatchResultsRow = document.getElementById('no-match-search-results');
    const matchesCountDisplay = document.getElementById('matches-count-display');

    if (matchesTable && (matchSearchInput || matchTournamentFilter || matchSportFilter || matchStatusFilter)) {
        function filterMatchesTable() {
            const query = matchSearchInput ? matchSearchInput.value.toLowerCase().trim() : '';
            const selectedTournamentId = matchTournamentFilter ? matchTournamentFilter.value : '';
            const selectedSportId = matchSportFilter ? matchSportFilter.value : '';
            const selectedStatus = matchStatusFilter ? matchStatusFilter.value.toLowerCase() : '';
            const rows = matchesTable.querySelectorAll('tbody tr:not(#no-match-search-results)');
            let visibleCount = 0;
            const totalCount = rows.length;

            rows.forEach(function (row) {
                const tournamentName = (row.getAttribute('data-tournament-name') || '').toLowerCase();
                const sportName = (row.getAttribute('data-sport-name') || '').toLowerCase();
                const team1Name = (row.getAttribute('data-team1-name') || '').toLowerCase();
                const team2Name = (row.getAttribute('data-team2-name') || '').toLowerCase();
                const venue = (row.getAttribute('data-match-venue') || '').toLowerCase();
                const tournamentId = row.getAttribute('data-tournament-id') || '';
                const sportId = row.getAttribute('data-sport-id') || '';
                const status = (row.getAttribute('data-match-status') || '').toLowerCase();

                const matchesQuery = query === '' || 
                    tournamentName.includes(query) || 
                    sportName.includes(query) || 
                    team1Name.includes(query) || 
                    team2Name.includes(query) || 
                    venue.includes(query);

                const matchesTournament = selectedTournamentId === '' || tournamentId === selectedTournamentId;
                const matchesSport = selectedSportId === '' || sportId === selectedSportId;
                const matchesStatus = selectedStatus === '' || status === selectedStatus;

                if (matchesQuery && matchesTournament && matchesSport && matchesStatus) {
                    row.style.display = '';
                    visibleCount++;
                } else {
                    row.style.display = 'none';
                }
            });

            if (noMatchResultsRow) {
                const isFiltered = query !== '' || selectedTournamentId !== '' || selectedSportId !== '' || selectedStatus !== '';
                noMatchResultsRow.style.display = (visibleCount === 0 && isFiltered) ? '' : 'none';
            }

            if (matchesCountDisplay) {
                matchesCountDisplay.textContent = `Showing ${visibleCount} of ${totalCount} matches`;
            }
        }

        if (matchSearchInput) {
            matchSearchInput.addEventListener('input', filterMatchesTable);
        }
        if (matchTournamentFilter) {
            matchTournamentFilter.addEventListener('change', filterMatchesTable);
        }
        if (matchSportFilter) {
            matchSportFilter.addEventListener('change', filterMatchesTable);
        }
        if (matchStatusFilter) {
            matchStatusFilter.addEventListener('change', filterMatchesTable);
        }
    }

    // --------------------------------------------------------
    // 16. Phase 5.5: Safe Delete Confirmation Dialog (Matches)
    // --------------------------------------------------------
    const deleteMatchForms = document.querySelectorAll('.delete-match-form');
    deleteMatchForms.forEach(function (form) {
        form.addEventListener('submit', function (event) {
            const matchInfo = form.getAttribute('data-match-info') || 'this match';
            const confirmed = window.confirm(
                `Are you sure you want to delete ${matchInfo}?\n\nThis action cannot be undone. Matches with recorded results or player statistics cannot be deleted.`
            );
            if (!confirmed) {
                event.preventDefault();
            }
        });
    });

    // --------------------------------------------------------
    // 17. Phase 5.5: Dynamic Team Options Filter in Match Form
    // --------------------------------------------------------
    const matchFormTournament = document.getElementById('match_tournament_id');
    const matchFormTeam1 = document.getElementById('match_team1_id');
    const matchFormTeam2 = document.getElementById('match_team2_id');

    if (matchFormTournament && matchFormTeam1 && matchFormTeam2) {
        function updateMatchTeamOptions() {
            const selectedOpt = matchFormTournament.options[matchFormTournament.selectedIndex];
            const sportId = selectedOpt ? selectedOpt.getAttribute('data-sport-id') : '';

            [matchFormTeam1, matchFormTeam2].forEach(function (selectEl) {
                const options = selectEl.querySelectorAll('option');
                options.forEach(function (opt) {
                    const optSportId = opt.getAttribute('data-sport-id');
                    if (!optSportId) {
                        opt.style.display = ''; // placeholder
                    } else if (sportId && optSportId === sportId) {
                        opt.style.display = '';
                    } else {
                        opt.style.display = 'none';
                        if (opt.selected) {
                            selectEl.value = '';
                        }
                    }
                });
            });
        }

        matchFormTournament.addEventListener('change', updateMatchTeamOptions);
        updateMatchTeamOptions();
    }

    // --------------------------------------------------------
    // 18. Phase 5.6: Real-time Results Table Search & Filter
    // --------------------------------------------------------
    const resultsSearchInput = document.getElementById('results-search');
    const resultTournamentFilter = document.getElementById('result-tournament-filter');
    const resultSportFilter = document.getElementById('result-sport-filter');
    const resultOutcomeFilter = document.getElementById('result-outcome-filter');
    const resultsTable = document.getElementById('results-table');
    const noResultResultsRow = document.getElementById('no-result-search-results');
    const resultsCountDisplay = document.getElementById('results-count-display');

    if (resultsTable && (resultsSearchInput || resultTournamentFilter || resultSportFilter || resultOutcomeFilter)) {
        function filterResultsTable() {
            const query = resultsSearchInput ? resultsSearchInput.value.toLowerCase().trim() : '';
            const selectedTournamentId = resultTournamentFilter ? resultTournamentFilter.value : '';
            const selectedSportId = resultSportFilter ? resultSportFilter.value : '';
            const selectedOutcome = resultOutcomeFilter ? resultOutcomeFilter.value.toLowerCase() : '';
            const rows = resultsTable.querySelectorAll('tbody tr:not(#no-result-search-results)');
            let visibleCount = 0;
            const totalCount = rows.length;

            rows.forEach(function (row) {
                const tournamentName = (row.getAttribute('data-tournament-name') || '').toLowerCase();
                const sportName = (row.getAttribute('data-sport-name') || '').toLowerCase();
                const team1Name = (row.getAttribute('data-team1-name') || '').toLowerCase();
                const team2Name = (row.getAttribute('data-team2-name') || '').toLowerCase();
                const venue = (row.getAttribute('data-match-venue') || '').toLowerCase();
                const tournamentId = row.getAttribute('data-tournament-id') || '';
                const sportId = row.getAttribute('data-sport-id') || '';
                const outcome = (row.getAttribute('data-result-outcome') || '').toLowerCase();

                const matchesQuery = query === '' || 
                    tournamentName.includes(query) || 
                    sportName.includes(query) || 
                    team1Name.includes(query) || 
                    team2Name.includes(query) || 
                    venue.includes(query);

                const matchesTournament = selectedTournamentId === '' || tournamentId === selectedTournamentId;
                const matchesSport = selectedSportId === '' || sportId === selectedSportId;
                const matchesOutcome = selectedOutcome === '' || outcome === selectedOutcome;

                if (matchesQuery && matchesTournament && matchesSport && matchesOutcome) {
                    row.style.display = '';
                    visibleCount++;
                } else {
                    row.style.display = 'none';
                }
            });

            if (noResultResultsRow) {
                const isFiltered = query !== '' || selectedTournamentId !== '' || selectedSportId !== '' || selectedOutcome !== '';
                noResultResultsRow.style.display = (visibleCount === 0 && isFiltered) ? '' : 'none';
            }

            if (resultsCountDisplay) {
                resultsCountDisplay.textContent = `Showing ${visibleCount} of ${totalCount} results`;
            }
        }

        if (resultsSearchInput) {
            resultsSearchInput.addEventListener('input', filterResultsTable);
        }
        if (resultTournamentFilter) {
            resultTournamentFilter.addEventListener('change', filterResultsTable);
        }
        if (resultSportFilter) {
            resultSportFilter.addEventListener('change', filterResultsTable);
        }
        if (resultOutcomeFilter) {
            resultOutcomeFilter.addEventListener('change', filterResultsTable);
        }
    }

    // --------------------------------------------------------
    // 19. Phase 5.6: Result Form Dynamic Outcome Preview
    // --------------------------------------------------------
    const score1Input = document.getElementById('team1_score');
    const score2Input = document.getElementById('team2_score');
    const outcomePreview = document.getElementById('outcome-preview-badge');
    const tieBreakContainer = document.getElementById('tie-break-container');
    const tieBreakNotesRequired = document.getElementById('tie-break-notes-required');

    if (score1Input && score2Input && outcomePreview) {
        function updateOutcomePreview() {
            const s1Val = score1Input.value.trim();
            const s2Val = score2Input.value.trim();

            if (s1Val === '' || s2Val === '' || isNaN(s1Val) || isNaN(s2Val)) {
                outcomePreview.textContent = 'Pending Scores';
                outcomePreview.className = 'badge-status badge-status-completed';
                if (tieBreakContainer) tieBreakContainer.style.display = 'none';
                return;
            }

            const s1 = parseInt(s1Val, 10);
            const s2 = parseInt(s2Val, 10);
            const team1Name = score1Input.getAttribute('data-team-name') || 'Team 1';
            const team2Name = score2Input.getAttribute('data-team-name') || 'Team 2';

            if (s1 > s2) {
                outcomePreview.textContent = `Winner: ${team1Name}`;
                outcomePreview.className = 'badge-status badge-outcome-win';
                if (tieBreakContainer) tieBreakContainer.style.display = 'none';
            } else if (s2 > s1) {
                outcomePreview.textContent = `Winner: ${team2Name}`;
                outcomePreview.className = 'badge-status badge-outcome-win';
                if (tieBreakContainer) tieBreakContainer.style.display = 'none';
            } else {
                outcomePreview.textContent = 'Scores Tied / Draw';
                outcomePreview.className = 'badge-status badge-outcome-draw';
                if (tieBreakContainer) tieBreakContainer.style.display = '';
            }
        }

        score1Input.addEventListener('input', updateOutcomePreview);
        score2Input.addEventListener('input', updateOutcomePreview);
        updateOutcomePreview();
    }

    // --------------------------------------------------------
    // 19. Phase 5.7: Tournament Standings Switcher
    // --------------------------------------------------------
    const tournamentSwitcher = document.getElementById('standings-tournament-switcher');
    if (tournamentSwitcher) {
        tournamentSwitcher.addEventListener('change', function () {
            const tournamentId = this.value;
            if (tournamentId) {
                window.location.href = `/admin/tournaments/${tournamentId}/standings`;
            }
        });
    }

    // --------------------------------------------------------
    // 20. Phase 9: UI/UX Consequential Action Confirmations & Keyboard UX
    // --------------------------------------------------------
    // Generic data-confirm attribute support
    document.addEventListener('submit', function (e) {
        const form = e.target;
        const confirmMsg = form.getAttribute('data-confirm');
        if (confirmMsg) {
            if (!window.confirm(confirmMsg)) {
                e.preventDefault();
                return false;
            }
        }
    });

    // Confirmation for User Status Toggle (Deactivate / Activate)
    document.querySelectorAll('form[action*="/status"]').forEach(function (form) {
        form.addEventListener('submit', function (e) {
            const isDeactivate = form.querySelector('input[name="status"][value="deactivate"]');
            const actionText = isDeactivate ? 'deactivate' : 'activate';
            const confirmed = window.confirm(`Are you sure you want to ${actionText} this user account?`);
            if (!confirmed) {
                e.preventDefault();
            }
        });
    });

    // Confirmation for User Role Change
    document.querySelectorAll('form[action*="/role"]').forEach(function (form) {
        form.addEventListener('submit', function (e) {
            const roleInput = form.querySelector('input[name="role"]');
            const targetRole = roleInput ? roleInput.value : 'the requested role';
            const confirmed = window.confirm(`Are you sure you want to change this user's role to ${targetRole}?`);
            if (!confirmed) {
                e.preventDefault();
            }
        });
    });

    // Keyboard support: Escape key dismisses open alert banners
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
            const firstAlert = document.querySelector('.alert');
            if (firstAlert) {
                firstAlert.remove();
            }
        }
    });

});




