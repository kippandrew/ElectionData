from shiny import App, reactive, render, ui, run_app
from shinywidgets import render_widget, output_widget
import pandas as pd
import geopandas as gpd
import matplotlib.cm as cm
import matplotlib.colors as clr
import matplotlib.pyplot as plt

# set pandas options
pd.options.display.max_columns = 10
pd.options.display.width = 120
pd.options.mode.copy_on_write = True

# define election years (not all supported)
election_years = [2024]

# load precincts shapes from ESRI shapefile
precincts = gpd.read_file("data/Clatsop_Precincts.shp")
precincts['Precinct_N'] = precincts['Precinct_N'].astype(int)

app_ui = ui.page_fillable(
    ui.card(
        ui.card_header("Election Results Explorer"),
        ui.layout_sidebar(
            ui.sidebar(
                ui.input_select(
                    "select_year",
                    "Select Election Year",
                    choices=election_years,
                    selected=2024
                ),
                ui.input_select("select_race",
                                "Select Election",
                                choices=[]),  # will be populated by the server function
                width=350
            ),
            ui.navset_card_underline(
                ui.nav_menu("Map ",
                            ui.nav_panel("Election Results",
                                         ui.output_plot("results_plot_candidate", height="400px")),
                            ui.nav_panel("Election Results (Party)",
                                         ui.output_plot("results_plot_party", height="400px")),
                            ),
                ui.nav_panel("Table",
                             ui.output_data_frame("results_table")),
                title="Election Results"
            )
        )
    )
)


def is_partisan(results):
    return results['Party'].any()


def server(input, output, session):
    @reactive.calc
    def calculate_results():
        election_results = pd.read_csv(f"data/{input.select_year()}_Clatsop_Precinct.csv")
        election_results = election_results[election_results['Race'] == input.select_race()]
        election_results = election_results[~election_results['Precinct'].str.contains('Total')]

        if is_partisan(election_results):
            # Gather results for the two major parties
            major_parties = election_results[election_results['Party'].isin(['Democratic Party',
                                                                             'Republican Party'])]

            # Aggregate results for all minor parties and write-ins into a single row
            minor_parties = election_results[~election_results['Party'].isin(['Democratic Party',
                                                                              'Republican Party'])]
            minor_parties['Party'] = 'Other'
            minor_parties['Name'] = 'Other / Write-In'
            minor_parties = minor_parties.groupby(['Race',
                                                   'Precinct',
                                                   'PrecinctCode',
                                                   'Party',
                                                   'Name'])['Votes'].sum().reset_index()

            race_results = pd.concat([major_parties, minor_parties])
        else:
            race_results = election_results.copy()

        # Calculate the percentage of votes for each candidate in each precinct
        race_results['VotePct'] = race_results.groupby(['Precinct'])['Votes'].transform(lambda x: x / x.sum())

        # Sort the results by precinct and candidate name
        race_results.sort_values(by=['Precinct', 'Party', 'Name'], inplace=True)

        return race_results

    @reactive.effect
    def select_year():
        df = pd.read_csv(f"data/{input.select_year()}_Clatsop_Precinct.csv")
        choices = list(df['Race'].unique())
        return ui.update_select("select_race", choices=choices, selected=choices[0])

    @render.plot()
    def results_plot_candidate():
        results = calculate_results()

        # Pivot the data by candidate to have separate columns for each candidate
        candidate_results = results.pivot_table(index=['Precinct', 'PrecinctCode'],
                                                columns='Name',
                                                values='VotePct').reset_index()


        # Determine the winner of each precinct
        candidate_results['Winner'] = candidate_results.iloc[:, 2:].idxmax(axis=1)

        # if is_partisan(results):
        #     candidate_results['WinnerParty'] = results

        print(candidate_results.to_string())

        # Merge the results with the precinct shapefile data
        precinct_data = precincts.merge(candidate_results, left_on='Precinct_N', right_on='PrecinctCode')

        fig, ax = plt.subplots()
        ax.set_title('Precincts Results (by Candidate)')
        ax.set_axis_off()

        precinct_data.plot(column='Winner',
                           cmap=cm.get_cmap('bwr').reversed() if is_partisan(results) else 'tab20',
                           edgecolor='black',
                           linewidth=0.3,
                           ax=ax,
                           legend=True,
                           alpha=1.0)
        return fig


    @render.plot()
    def results_plot_party():
        results = calculate_results()

        # Pivot the data by party to have separate columns for Democratic, Republican and Other Party votes
        party_results = results.pivot_table(index=['Precinct', 'PrecinctCode'],
                                            columns='Party',
                                            values='VotePct').reset_index()

        # Name the columns
        party_results.rename(
            columns={'Democratic Party': 'DemVotePct',
                     'Republican Party': 'RepVotePct',
                     'Other Party': 'OtherPct'},
            inplace=True)

        # Calculate the margin of victory for each party
        party_results['DemMarginPct'] = party_results['DemVotePct'] - party_results['RepVotePct']
        party_results['RepMarginPct'] = party_results['RepVotePct'] - party_results['DemVotePct']

        # Merge the results with the precinct shapefile data
        precinct_data = precincts.merge(party_results, left_on='Precinct_N', right_on='PrecinctCode')

        rep_min = party_results['RepMarginPct'].min()
        rep_max = party_results['RepMarginPct'].max()
        print(rep_min, rep_max)
        rep_divnorm = clr.TwoSlopeNorm(vmin=rep_min, vcenter=0.0, vmax=rep_max)

        dem_min = party_results['RepMarginPct'].min()
        dem_max = party_results['RepMarginPct'].max()
        dem_divnorm = clr.TwoSlopeNorm(vmin=dem_min, vcenter=0.0, vmax=dem_max)

        # Plot the choropleth map
        fig, ax = plt.subplots()
        ax.set_title('Precincts Results (by Party)')
        ax.set_axis_off()
        precinct_data.plot(column='RepMarginPct',
                           cmap='bwr',
                           edgecolor='black',
                           linewidth=0.2,
                           ax=ax,
                           legend=True,
                           alpha=1.0,
                           norm=rep_divnorm)
        return fig

    @render.data_frame
    def results_table():
        df = calculate_results().copy()

        # format the percentage columns
        df['VotePct'] = df['VotePct'].map('{:.2%}'.format)

        display_columns = ['Precinct', 'Name', 'Party', 'Votes', 'VotePct']

        return render.DataGrid(
            df[display_columns],
            width="100%"
        )


app = App(app_ui, server)

if __name__ == '__main__':
    run_app('app:app', reload=True)
