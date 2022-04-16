import math
import operator

from setup import *


def start_applications(edge_computing_systems: list, applications: list, processing_time: int,
                       global_applications: bool, degradable_applications: bool, degradable_multiplier,
                       diagnostics: bool):
    """
    :param edge_computing_systems: list of nodes
    :param applications: list of applications
    :param processing_time: current second of simulation time
    :param global_applications: determines if applications can start at any server or not
    :param degradable_applications: determines if applications can scale based on available cores
    :param diagnostics: determines whether to print information to console
    :return: None
    """
    """Start applications on a server for the first time"""
    powered_servers = (server for node in edge_computing_systems for server in node.servers if server.on is True)
    for server in powered_servers:
        if server.cores > 0 and server.memory > 0:
            for app in list(applications[:1000]):
                if (app.memory <= server.memory and app.cores <= server.cores and global_applications
                    and not degradable_applications) or (app.memory <= server.memory and app.cores <= server.cores and
                                                         server.parent.index == 0 and not degradable_applications):
                    app.start_time = processing_time
                    print(app.time_left)
                    server.start_application(app)
                    applications.remove(app)
                    if diagnostics:
                        print('started', app, 'from', app.parent, 'on', app.parent.parent)
                # criteria for degradable applications
                elif (app.memory <= server.memory and global_applications and degradable_applications) \
                        or (app.memory <= server.memory and degradable_applications and server.parent.index == 0):
                    app.start_time = processing_time
                    app.cores = server.cores if server.cores <= app.original_cores * degradable_multiplier \
                        else app.original_cores * degradable_multiplier
                    app.time_left = app.runtime * app.original_cores / app.cores
                    print(app.time_left)
                    server.start_application(app)
                    applications.remove(app)
                    if diagnostics:
                        print('started', app, 'from', app.parent, 'on', app.parent.parent)


def complete_applications(edge_computing_systems: list, completed_applications: list, processing_time: int,
                          diagnostics: bool):
    """
    :param edge_computing_systems: list of nodes
    :param completed_applications: list of completed applications
    :param processing_time: current time
    :param diagnostics: determines whether to print information to console
    :return: None
    """
    """Removes applications from servers once they finish running"""
    current_completed = 0
    powered_servers = (server for node in edge_computing_systems for server in node.servers if server.on is True)
    for server in powered_servers:
        for application in list(server.applications_running):
            application.time_left -= 1
            if application.time_left <= 0:
                application.end_time = processing_time
                server.stop_application(application)
                current_completed += 1
                application.parent.parent.applications_completed += 1
                completed_applications.append(application)
                if diagnostics:
                    print(f'completed {application} on Node {application.parent.parent.index}')
    return current_completed


def power_servers(edge_computing_systems: list):
    """
    :param edge_computing_systems: list of nodes
    :return: None
    """
    """Helper function that turns on all servers"""
    powered_servers = (server for edge in edge_computing_systems for server in edge.servers)
    for server in powered_servers:
        server.on = True


def shutdown_servers(edge_computing_systems: list, power_per_server: float, irradiance_list: tuple,
                     processing_time: int, partially_completed_applications: list, diagnostics: bool):
    """
    :param edge_computing_systems: list of nodes
    :param power_per_server: power that each server needs to operate, in W
    :param irradiance_list: tuple of irradiance values for each node
    :param processing_time: simulated time, in seconds
    :param partially_completed_applications: list of applications that have been paused
    :param diagnostics: determines whether to print information to console
    :return: None
    """
    """Determines which servers to power off"""
    current_paused = 0
    power_servers(edge_computing_systems)
    # turn off servers w/o enough power (priority to keep servers on that are closest to completing a task)
    for edge in edge_computing_systems:
        servers_on = len(edge.servers)
        power = edge.get_power_generated(irradiance_list[processing_time][edge.index])  # update power available
        battery_power = edge.current_battery
        max_power_available = power + battery_power
        most_servers_on = math.floor((power + battery_power) / power_per_server)
        if servers_on > most_servers_on:
            shortest_apps = []
            for server in edge.servers:
                if not server.applications_running and server.on is True:
                    server.on = False
                    servers_on -= 1
                    max_power_available -= power_per_server
                    if servers_on <= most_servers_on:
                        break
                else:
                    shortest_apps.append(min(server.applications_running, key=operator.attrgetter('time_left')))
            for app in sorted(shortest_apps, key=operator.attrgetter('time_left'))[most_servers_on - servers_on:]:
                app.parent.on = False
                servers_on -= 1
                max_power_available -= power_per_server
                shortest_apps.remove(app)
                for running_app in app.parent.applications_running:
                    app.parent.stop_application(running_app)
                    partially_completed_applications.insert(0, running_app)
                    current_paused += 1
                    if diagnostics:
                        print('pausing', running_app, running_app.time_left, 'on', running_app.parent.parent)
    return current_paused


def resume_applications(policy: str, location_distances: dict, applications: list, shortest_distances: dict,
                        cost_multiplier: float, edge_computing_systems: list, irradiance_list: list,
                        processing_time: int, power_per_server: float, degradable_applications: bool,
                        degradable_multiplier, diagnostics: bool):
    """
    :param policy: decides which task transfer policy to use
    :param location_distances: distances in km between nodes
    :param applications: list of applications
    :param shortest_distances: dictionary of (dictionary of node:(closest node,distance) pairs)
    :param cost_multiplier: constant in calculating delay
    :param edge_computing_systems: list of all edge sites that are part of the edge computing system
    :param irradiance_list: list of solar irradiance tuples
    :param processing_time: simulated time
    :param power_per_server: power each server consumes
    :param degradable_applications: determines if applications can scale based on available cores
    :param diagnostics: determines whether to print information to console
    :return: None
    """

    def passive():
        current_migrations = 0
        for app in list(applications):
            app.overhead += 1
            if degradable_applications and app.parent.on and app.parent.cores > 0 and app.memory <= app.parent.memory:
                prev_cores = app.cores
                app.cores = app.parent.cores if app.parent.cores <= app.original_cores * degradable_multiplier \
                    else app.original_cores * degradable_multiplier
                app.time_left = app.time_left * prev_cores / app.cores
                if diagnostics:
                    print(f'resume app:{app} on {app.parent.parent}')
                app.parent.start_application(app)
                app.delay = None
                app.overhead -= 1
                applications.remove(app)
            elif app.parent.on and app.cores <= app.parent.cores and \
                    app.memory <= app.parent.memory:
                if diagnostics:
                    print(f'resume app:{app} on {app.parent.parent}')
                print(f'resume app:{app} on {app.parent.parent.index} at time {processing_time}')
                app.parent.start_application(app)
                app.delay = None
                app.overhead -= 1
                applications.remove(app)
        return current_migrations

    def greedy():
        current_migrations = 0
        for app in list(applications):
            app.overhead += 1
            if app.delay is None:
                options = []
                for node in edge_computing_systems:
                    power = node.get_power_generated(irradiance_list[processing_time][node.index])
                    if app.parent.parent == node:
                        delay = 0
                    else:
                        try:
                            delay = calculate_delay(cost_multiplier, math.ceil(
                                location_distances[(app.parent.parent, node)]), app.memory)
                        except KeyError:
                            delay = calculate_delay(cost_multiplier, math.ceil(
                                location_distances[(node, app.parent.parent)]), app.memory)
                    if delay == 0:
                        options.append((power, delay, node, 'wait'))
                    else:
                        options.append((power, delay, node, 'transfer'))
                print('options', options)
                if policy == 'greedy':
                    try:
                        best_choice = max((option for option in options if option[0] >= power_per_server),
                                          key=lambda n: (-n[1], n[0]))
                    except ValueError:
                        best_choice = max(options, key=lambda n: (n[0], -n[1]))
                else:
                    best_choice = max(options, key=lambda n: (n[0], -n[1]))
                print('best', best_choice)
                app.delay = best_choice[1]
                app.prev_parent = app.parent
                app.parent = best_choice[2].servers[0]
            elif app.delay > 0:
                app.delay -= 1
            if app.delay <= 0:
                for server in app.parent.parent.servers:
                    if server.on and degradable_applications and server.cores > 0 and app.memory <= server.memory:
                        prev_cores = app.cores
                        app.cores = server.cores if server.cores <= app.original_cores * degradable_multiplier \
                            else app.original_cores * degradable_multiplier
                        app.time_left = app.time_left * prev_cores / app.cores
                        if diagnostics:
                            print(f'resume app:{app} on {server.parent}')
                        server.start_application(app)
                        if app.prev_parent != app.parent:
                            current_migrations += 1
                        app.delay = None
                        app.overhead -= 1
                        applications.remove(app)
                        break
                    elif server.on is True and app.cores <= server.cores and app.memory <= server.memory:
                        if diagnostics:
                            print(f'resume app:{app} on {server.parent}')
                        print(f'resume app:{app} on {server.parent.index} at time {processing_time}')
                        server.start_application(app)
                        if app.prev_parent != app.parent:
                            current_migrations += 1
                        app.delay = None
                        app.overhead -= 1
                        applications.remove(app)
                        break
        return current_migrations

    def yolo():
        current_migrations = 0
        for app in list(applications):
            app.overhead += 1
            if app.delay is None:
                app.delay = calculate_delay(cost_multiplier, shortest_distances[app.parent.parent][1], app.memory)
            elif app.delay > 0:
                app.delay -= 1
            if app.delay <= 0:
                for server in shortest_distances[app.parent.parent][0].servers:
                    if server.on and degradable_applications and server.cores > 0 and app.memory <= server.memory:
                        prev_cores = app.cores
                        app.cores = server.cores if server.cores <= app.original_cores * degradable_multiplier \
                            else app.original_cores * degradable_multiplier
                        app.time_left = app.time_left * prev_cores / app.cores
                        if diagnostics:
                            print(f'resume app:{app}, from {app.parent.parent} to {server.parent} at time '
                                  f'{processing_time}')
                        server.start_application(app)
                        current_migrations += 1
                        app.delay = None
                        app.overhead -= 1
                        applications.remove(app)
                        break
                    elif server.on is True and app.cores <= server.cores and app.memory <= server.memory:
                        if diagnostics:
                            print(f'resume app:{app}, from {app.parent.parent} to {server.parent} at time '
                                  f'{processing_time}')
                        server.start_application(app)
                        current_migrations += 1
                        app.delay = None
                        app.overhead -= 1
                        applications.remove(app)
                        break
        return current_migrations

    def look_ahead():
        current_migrations = 0
        for app in list(applications):
            app.overhead += 1
            if app.delay is None:
                options = []
                for node in edge_computing_systems:
                    if node == app.parent.parent:
                        delay = 0
                    else:
                        try:
                            delay = calculate_delay(cost_multiplier, location_distances[(app.parent.parent, node)],
                                                    app.memory)
                        except KeyError:
                            delay = calculate_delay(cost_multiplier, location_distances[(node, app.parent.parent)],
                                                    app.memory)
                    future_processing_time = processing_time + delay
                    for time_stamp in range(86400):
                        power = node.get_power_generated(irradiance_list[future_processing_time][node.index])
                        if power >= power_per_server:
                            if app.parent.parent == node:
                                options.append((power, future_processing_time - processing_time, node.index, 'wait'))
                            else:
                                options.append((power, future_processing_time - processing_time, node.index,
                                                'transfer'))
                        future_processing_time += 1
                        if power >= power_per_server:
                            break
                print('time', processing_time)
                print('options', options)
                try:
                    min_delay = min(options, key=lambda n: (n[1], -n[0]))[1]
                    better_options = [choice for choice in options if choice[1] == min_delay]
                    print('better', better_options)
                    for index, option in enumerate(better_options):
                        if index == 0:
                            best_choice = option
                        if option[3] == 'wait':
                            best_choice = option
                    print('best', best_choice)
                    app.delay = best_choice[1]
                    app.prev_parent = app.parent
                    app.parent = edge_computing_systems[best_choice[2]].servers[0]
                except ValueError:
                    app.delay = 0
            else:
                if app.delay > 0:
                    app.delay -= 1
                if app.delay <= 0:
                    for server in app.parent.parent.servers:
                        if server.on and degradable_applications and server.cores > 0 and app.memory <= server.memory:
                            prev_cores = app.cores
                            app.cores = server.cores if server.cores <= app.original_cores * degradable_multiplier \
                                else app.original_cores * degradable_multiplier
                            app.time_left = app.time_left * prev_cores / app.cores
                            server.start_application(app)
                            if diagnostics:
                                print(f'resume app:{app} on node {server.parent.index} at time {processing_time}')
                            app.parent = server
                            app.delay = None
                            app.overhead -= 1
                            print(app.time_left)
                            applications.remove(app)
                            break
                        elif server.on and app.cores <= server.cores and app.memory <= server.memory:
                            if diagnostics:
                                print(f'resume app:{app} on node {server.parent.index} at time {processing_time}')
                            print(f'resume app:{app} on {server.parent.index} at time {processing_time}')
                            server.start_application(app)
                            if app.prev_parent != app.parent:
                                current_migrations += 1
                            app.parent = server
                            app.delay = None
                            app.overhead -= 1
                            print(app.time_left)
                            applications.remove(app)
                            break
        return current_migrations

    def practical():
        current_migrations = 0
        for app in list(applications):
            app.overhead += 1
            if app.delay is None:
                options = []
                for node in edge_computing_systems:
                    if node == app.parent.parent:
                        delay = 0
                    else:
                        try:
                            delay = calculate_delay(cost_multiplier, location_distances[(app.parent.parent, node)],
                                                    app.memory)
                        except KeyError:
                            delay = calculate_delay(cost_multiplier, location_distances[(node, app.parent.parent)],
                                                    app.memory)
                    yesterday_irradiance1 = [value[node.index] for value in irradiance_list][
                                            processing_time - 90000: processing_time - 86400]
                    yesterday_irradiance2 = [value[node.index] for value in irradiance_list][
                                            processing_time - 86400: processing_time - 82800]
                    today_irradiance1 = [value[node.index] for value in irradiance_list][
                                        processing_time - 3600: processing_time]

                    if not yesterday_irradiance1:
                        yesterday_irradiance1 = [value[node.index] for value in irradiance_list][
                                                0: processing_time]
                    if not yesterday_irradiance2:
                        yesterday_irradiance2 = [value[node.index] for value in irradiance_list][
                                                0: processing_time]

                    avg_yesterday_irradiance1 = sum(yesterday_irradiance1) / len(yesterday_irradiance1)
                    avg_yesterday_irradiance2 = sum(yesterday_irradiance2) / len(yesterday_irradiance2)
                    avg_today_irradiance1 = sum(today_irradiance1) / len(today_irradiance1)

                    if avg_yesterday_irradiance1 > 0:
                        irradiance = avg_yesterday_irradiance2 * avg_today_irradiance1 / avg_yesterday_irradiance1
                    else:
                        irradiance = 0

                    estimated_power = node.get_power_generated(irradiance)

                    if node == app.parent.parent:
                        wait_option = (estimated_power, delay, node.index, 'wait')

                    if estimated_power >= power_per_server:
                        if app.parent.parent == node:
                            options.append((estimated_power, delay, node.index, 'wait'))
                        else:
                            options.append((estimated_power, delay, node.index, 'transfer'))
                print('time', processing_time)
                print('options', options)

                if options:
                    min_delay = min(options, key=lambda n: (n[1], -n[0]))[1]  # minimize delay, maximize power
                    better_options = [choice for choice in options if choice[1] == min_delay]
                else:
                    better_options = [wait_option]  # wait if no option has power
                print('better', better_options)
                for index, option in enumerate(better_options):
                    if index == 0:
                        best_choice = option
                    if option[3] == 'wait':
                        best_choice = option
                app.delay = best_choice[1]
                print('best', best_choice)
                app.prev_parent = app.parent
                app.parent = edge_computing_systems[best_choice[2]].servers[0]
            elif app.delay > 0:
                app.delay -= 1
            if app.delay <= 0:
                for server in app.parent.parent.servers:
                    if server.on and degradable_applications and server.cores > 0 and app.memory <= server.memory:
                        prev_cores = app.cores
                        app.cores = server.cores if server.cores <= app.original_cores * degradable_multiplier \
                            else app.original_cores * degradable_multiplier
                        app.time_left = app.time_left * prev_cores / app.cores
                        server.start_application(app)
                        if diagnostics:
                            print(f'resume app:{app} on node {server.parent.index} at time {processing_time}')
                        if app.prev_parent != app.parent:
                            app.delay = None
                        app.overhead -= 1
                        applications.remove(app)
                        break
                    elif server.on and app.cores <= server.cores and app.memory <= server.memory:
                        server.start_application(app)
                        current_migrations += 1
                        if diagnostics:
                            print(f'resume app:{app} on {server.parent} {server.parent.index}')
                        print(f'resume app:{app} on {server.parent.index} at time {processing_time}')
                        if app.prev_parent != app.parent:
                            app.delay = None
                        app.overhead -= 1
                        applications.remove(app)
                        break
        return current_migrations

    if policy == 'YOLO':
        return yolo()
    elif policy == 'passive':
        return passive()
    elif policy == 'greedy' or policy == 'super-greedy':
        return greedy()
    elif policy == 'look-ahead':
        return look_ahead()
    elif policy == 'practical':
        return practical()


def update_batteries(edge_computing_systems: list, power_per_server: float, irradiance_list: tuple,
                     processing_time: int):
    """
    :param edge_computing_systems: list of nodes
    :param power_per_server: power each server consumes
    :param irradiance_list: list of solar irradiance tuples
    :param processing_time: simulated time
    :return: None
    """
    """Adds power to node's battery if not used in this time period"""
    # power off servers without applications running
    for node in edge_computing_systems:
        for server in node.servers:
            if server.on is True and not server.applications_running:
                server.on = False

    # calculate leftover power per node
    for node in edge_computing_systems:
        power = node.get_power_generated(irradiance_list[processing_time][node.index])  # update power available
        for server in node.servers:
            if server.on is True:
                power -= power_per_server
        if node.current_battery + power <= node.max_battery:
            node.current_battery += power
        else:
            node.current_battery = node.max_battery


def calculate_delay(equation, distance, memory):
    memory *= 8  # convert MB to Mb
    equation = equation.replace('x', str(distance))
    try:
        equation = eval(equation)
        delay = math.ceil(memory / equation)
    except ZeroDivisionError:
        delay = 0
    return delay
