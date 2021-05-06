/* creates a dataTable object for a contracts table*/
function createContractsDataTable(tab_name, view_url) {
    const DATETIME_FORMAT_2 = 'YYYY-MMM-DD HH:mm'
    const columns = [
        { data: 'status' },
        {
            data: 'start_location',
            render: {
                _: 'display',
                sort: 'sort'
            }
        },
        {
            data: 'end_location',
            render: {
                _: 'display',
                sort: 'sort'
            }
        },
        {
            data: 'reward',
            render: $.fn.dataTable.render.formatisk()
        },
        {
            data: 'collateral',
            render: $.fn.dataTable.render.formatisk()
        },
        {
            data: 'volume',
            render: $.fn.dataTable.render.number(',', '.', 0)
        },
        { data: 'pricing_check' },
        {
            data: 'date_issued',
            render: $.fn.dataTable.render.moment(moment.ISO_8601, DATETIME_FORMAT_2)
        },
        {
            data: 'date_expired',
            render: $.fn.dataTable.render.moment(moment.ISO_8601, DATETIME_FORMAT_2)
        },
        { data: 'issuer' },
        {
            data: 'date_accepted',
            render: $.fn.dataTable.render.moment(moment.ISO_8601, DATETIME_FORMAT_2)
        },
        { data: 'acceptor' },

        /* hidden columns for filter */
        { data: 'route_name' }
    ];
    const columnDefs = [
        { "orderable": false, "targets": [6] },
        { "visible": false, "targets": [12] }
    ];
    const order = [[7, "desc"]];
    const filterDropDown = {
        columns: [
            {
                idx: 12,
                title: 'Route'
            },
            {
                idx: 0
            },
            {
                idx: 9
            },
            {
                idx: 11
            }
        ],
        bootstrap: true,
        autoSize: false
    };
    const createdRow = function (row, data, dataIndex) {
        if (data['is_in_progress']) {
            $(row).addClass('info');
        }
        else if (data['is_failed']) {
            $(row).addClass('warning');
        }
        else if (data['is_completed']) {
            $(row).addClass('success');
        }
    };
    $("#" + tab_name).DataTable({
        ajax: {
            url: view_url, dataSrc: '', cache: false
        },
        columns: columns,
        columnDefs: columnDefs,
        order: order,
        filterDropDown: filterDropDown,
        createdRow: createdRow
    });
}
